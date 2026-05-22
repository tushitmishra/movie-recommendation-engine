"""
Recommendation helpers: collaborative filtering (user–user), content-based
TF-IDF vectorization + cosine similarity, mood-to-genre boosts, and hybrid fusion.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import requests
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize

logger = logging.getLogger(__name__)

# Mood labels → TMDB genre ids (multi-label)
MOOD_GENRES: Dict[str, List[int]] = {
    "chill": [18, 10402, 99],  # Drama, Music, Documentary
    "laugh": [35],
    "thrill": [53, 27, 80],  # Thriller, Horror, Crime
    "romance": [10749, 10751],
    "action": [28, 12],
    "family": [10751, 16],
    "scifi": [878, 9648],
    "fantasy": [14],
    "mystery": [9648, 80],
}


def _movie_text(m: Dict[str, Any]) -> str:
    genres = " ".join(g.get("name", "") for g in (m.get("genres") or []))
    title = m.get("title") or m.get("name") or ""
    overview = m.get("overview") or ""
    tagline = m.get("tagline") or ""
    return f"{title} {tagline} {genres} {overview}"


def _tmdb_get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def fetch_movie_detail(movie_id: int, api_key: str, base_url: str) -> Optional[Dict[str, Any]]:
    try:
        return _tmdb_get(f"{base_url}/movie/{movie_id}", {"api_key": api_key})
    except Exception as e:
        logger.warning("TMDB movie %s: %s", movie_id, e)
        return None


def _candidate_ids_from_tmdb(
    seed_ids: List[int],
    api_key: str,
    base_url: str,
    max_per_seed: int = 12,
    cap_total: int = 45,
) -> List[int]:
    seen: Set[int] = set(seed_ids)
    out: List[int] = []
    for sid in seed_ids[:4]:
        try:
            sim = _tmdb_get(f"{base_url}/movie/{sid}/similar", {"api_key": api_key})
            rec = _tmdb_get(f"{base_url}/movie/{sid}/recommendations", {"api_key": api_key})
            for src in (sim.get("results") or [])[:max_per_seed]:
                mid = src.get("id")
                if mid and mid not in seen:
                    seen.add(mid)
                    out.append(mid)
            for src in (rec.get("results") or [])[:max_per_seed]:
                mid = src.get("id")
                if mid and mid not in seen:
                    seen.add(mid)
                    out.append(mid)
        except Exception as e:
            logger.warning("similar/rec for seed %s: %s", sid, e)
        if len(out) >= cap_total:
            break
    return out[:cap_total]


def content_scores_tfidf_cosine(
    seed_details: List[Dict[str, Any]],
    candidate_details: List[Dict[str, Any]],
) -> Dict[int, float]:
    """TF-IDF vectorize overview+genres+title; profile = mean(seed vectors); score = cosine to profile."""
    seeds = [d for d in seed_details if d]
    cands = [d for d in candidate_details if d]
    if not seeds or not cands:
        return {}

    seed_texts = [_movie_text(m) for m in seeds]
    cand_texts = [_movie_text(m) for m in cands]
    all_texts = seed_texts + cand_texts
    vectorizer = TfidfVectorizer(
        max_features=8000,
        stop_words="english",
        ngram_range=(1, 2),
        min_df=1,
    )
    try:
        X = vectorizer.fit_transform(all_texts)
    except ValueError:
        return {}

    n_s = len(seed_texts)
    prof = X[:n_s].mean(axis=0)
    cand_mat = X[n_s:]
    sims = cosine_similarity(prof, cand_mat).ravel()
    scores: Dict[int, float] = {}
    for i, m in enumerate(cands):
        mid = m.get("id")
        if mid is not None:
            scores[int(mid)] = float(max(0.0, sims[i]))
    return scores


def collaborative_user_user_scores(
    target_user_id: str,
    ratings: List[Dict[str, Any]],
    min_rating: float = 6.0,
    top_k_similar: int = 20,
) -> Dict[int, float]:
    """
    User–user collaborative filtering: cosine similarity on users×movies rating matrix.
    Returns movie_id -> aggregated score from similar users' high ratings.
    """
    if not ratings:
        return {}

    user_ids: List[str] = []
    movie_ids: List[int] = []
    u_index: Dict[str, int] = {}
    m_index: Dict[int, int] = {}

    for r in ratings:
        uid = str(r.get("user_id", ""))
        mid = r.get("movie_id")
        val = r.get("rating")
        if uid is None or mid is None or val is None:
            continue
        try:
            mid = int(mid)
            val = float(val)
        except (TypeError, ValueError):
            continue
        if uid not in u_index:
            u_index[uid] = len(user_ids)
            user_ids.append(uid)
        if mid not in m_index:
            m_index[mid] = len(movie_ids)
            movie_ids.append(mid)

    n_u, n_m = len(user_ids), len(movie_ids)
    if n_u < 2 or n_m < 2:
        return {}

    rows, cols, data = [], [], []
    for r in ratings:
        uid = str(r.get("user_id", ""))
        mid = r.get("movie_id")
        val = r.get("rating")
        if uid not in u_index or mid not in m_index:
            continue
        try:
            mid = int(mid)
            val = float(val)
        except (TypeError, ValueError):
            continue
        rows.append(u_index[uid])
        cols.append(m_index[mid])
        data.append(val)

    R = csr_matrix((data, (rows, cols)), shape=(n_u, n_m))
    R_n = normalize(R, norm="l2", axis=1)
    sim_u = cosine_similarity(R_n, dense_output=True)

    if target_user_id not in u_index:
        return {}
    ti = u_index[target_user_id]
    seen_movies = set(R.getrow(ti).nonzero()[1].tolist())
    user_sim = sim_u[ti].copy()
    user_sim[ti] = -1.0
    top_neighbours = np.argsort(user_sim)[::-1][:top_k_similar]

    movie_scores: Dict[int, float] = {}
    movie_weights: Dict[int, float] = {}
    for j in top_neighbours:
        s = float(user_sim[j])
        if s <= 0:
            continue
        row = R.getrow(j)
        _, ind = row.nonzero()
        for mi in ind:
            if mi in seen_movies:
                continue
            rating_val = float(row[0, mi])
            if rating_val < min_rating:
                continue
            mid = movie_ids[mi]
            movie_scores[mid] = movie_scores.get(mid, 0.0) + s * rating_val
            movie_weights[mid] = movie_weights.get(mid, 0.0) + abs(s)

    for mid in list(movie_scores.keys()):
        w = movie_weights.get(mid, 0.0)
        if w > 0:
            movie_scores[mid] /= w
    return movie_scores


def apply_mood_boost(
    scores: Dict[int, float],
    movie_genre_map: Dict[int, List[int]],
    mood: Optional[str],
) -> Dict[int, float]:
    if not mood or mood not in MOOD_GENRES:
        return scores
    want = set(MOOD_GENRES[mood])
    boosted: Dict[int, float] = {}
    for mid, sc in scores.items():
        gids = set(movie_genre_map.get(mid, []))
        mult = 1.35 if gids & want else 1.0
        boosted[mid] = sc * mult
    return boosted


def normalize_scores(d: Dict[int, float]) -> Dict[int, float]:
    if not d:
        return {}
    mx = max(d.values())
    if mx <= 0:
        return d
    return {k: v / mx for k, v in d.items()}


def merge_hybrid(
    content: Dict[int, float],
    collab: Dict[int, float],
    w_content: float = 0.55,
    w_collab: float = 0.45,
) -> Dict[int, float]:
    keys = set(content.keys()) | set(collab.keys())
    out: Dict[int, float] = {}
    c_norm = normalize_scores(content)
    k_norm = normalize_scores(collab)
    for mid in keys:
        out[mid] = w_content * c_norm.get(mid, 0.0) + w_collab * k_norm.get(mid, 0.0)
    return out


def movies_to_tmdb_results(
    ordered_ids: List[int],
    detail_cache: Dict[int, Dict[str, Any]],
    api_key: str,
    base_url: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for mid in ordered_ids:
        if len(results) >= limit:
            break
        m = detail_cache.get(mid)
        if not m:
            m = fetch_movie_detail(mid, api_key, base_url)
            if m:
                detail_cache[mid] = m
        if m and m.get("id"):
            results.append(m)
    return results


def build_recommendations(
    *,
    user_id: str,
    watchlist: List[int],
    favorites: List[int],
    ratings: List[Dict[str, Any]],
    api_key: str,
    base_url: str,
    rec_type: str = "hybrid",
    mood: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    rec_type: hybrid | content | collaborative | mood
    """
    user_rated_ids = {int(r["movie_id"]) for r in ratings if str(r.get("user_id")) == user_id and r.get("movie_id") is not None}
    exclude: Set[int] = set(watchlist) | set(favorites) | user_rated_ids

    high_rated = [
        int(r["movie_id"])
        for r in ratings
        if str(r.get("user_id")) == user_id and float(r.get("rating") or 0) >= 7.5
    ]
    seed_ids = list(dict.fromkeys([*favorites, *watchlist, *high_rated]))[:8]
    if not seed_ids:
        seed_ids = list(watchlist[:1] or favorites[:1])
    if not seed_ids:
        try:
            tr = _tmdb_get(f"{base_url}/trending/movie/week", {"api_key": api_key})
            r0 = (tr.get("results") or [{}])[0]
            if r0.get("id"):
                seed_ids = [int(r0["id"])]
        except Exception as e:
            logger.warning("trending seed: %s", e)

    detail_cache: Dict[int, Dict[str, Any]] = {}

    # --- Collaborative ---
    collab_raw = collaborative_user_user_scores(user_id, ratings)
    collab_raw = {mid: s for mid, s in collab_raw.items() if mid not in exclude}

    # --- Content (TF-IDF + cosine) ---
    seed_details = []
    for sid in seed_ids[:6]:
        d = fetch_movie_detail(sid, api_key, base_url)
        if d:
            detail_cache[sid] = d
            seed_details.append(d)

    cand_ids = _candidate_ids_from_tmdb(seed_ids, api_key, base_url)
    cand_ids = [c for c in cand_ids if c not in exclude]

    cand_details: List[Dict[str, Any]] = []
    for cid in cand_ids:
        d = detail_cache.get(cid) or fetch_movie_detail(cid, api_key, base_url)
        if d:
            detail_cache[cid] = d
            cand_details.append(d)

    content_raw = content_scores_tfidf_cosine(seed_details, cand_details)
    content_raw = {mid: s for mid, s in content_raw.items() if mid not in exclude}

    movie_genre_map: Dict[int, List[int]] = {}
    for d in list(detail_cache.values()):
        mid = d.get("id")
        if mid:
            movie_genre_map[int(mid)] = [g.get("id") for g in (d.get("genres") or []) if g.get("id")]

    mood_key = (mood or "").lower().strip() or None
    if mood_key and mood_key in MOOD_GENRES:
        if rec_type == "content":
            content_raw = apply_mood_boost(content_raw, movie_genre_map, mood_key)
        elif rec_type == "collaborative":
            collab_raw = apply_mood_boost(collab_raw, movie_genre_map, mood_key)

    merged = merge_hybrid(content_raw, collab_raw)
    if mood_key and mood_key in MOOD_GENRES and rec_type in ("hybrid", "mood"):
        merged = apply_mood_boost(merged, movie_genre_map, mood_key)

    if rec_type == "content":
        ordered = sorted(content_raw.keys(), key=lambda x: content_raw[x], reverse=True)
    elif rec_type == "collaborative":
        ordered = sorted(collab_raw.keys(), key=lambda x: collab_raw[x], reverse=True)
    else:
        # hybrid, mood: merged already includes optional mood boost from query params
        ordered = sorted(merged.keys(), key=lambda x: merged[x], reverse=True)

    if not ordered:
        # fallback: first seed similar API
        if seed_ids:
            try:
                rec = _tmdb_get(
                    f"{base_url}/movie/{seed_ids[0]}/recommendations",
                    {"api_key": api_key},
                )
                for m in rec.get("results") or []:
                    mid = m.get("id")
                    if mid and mid not in exclude:
                        ordered.append(mid)
            except Exception as e:
                logger.warning("tmdb recommendations fallback: %s", e)

    if not ordered and mood_key and mood_key in MOOD_GENRES:
        try:
            gid = MOOD_GENRES[mood_key][0]
            disc = _tmdb_get(
                f"{base_url}/discover/movie",
                {
                    "api_key": api_key,
                    "with_genres": str(gid),
                    "sort_by": "popularity.desc",
                },
            )
            for m in disc.get("results") or []:
                mid = m.get("id")
                if mid and mid not in exclude:
                    ordered.append(mid)
        except Exception as e:
            logger.warning("discover mood fallback: %s", e)

    results = movies_to_tmdb_results(ordered, detail_cache, api_key, base_url, limit=limit)
    return {"page": 1, "results": results, "total_pages": 1, "total_results": len(results)}
