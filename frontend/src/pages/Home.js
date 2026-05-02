import { useState, useEffect, useCallback } from 'react';
import { movieApi } from '../api/movieApi';
import { useAuth } from '../contexts/AuthContext';
import { Link } from 'react-router-dom';
import { Play, Plus, ChevronLeft, ChevronRight } from 'lucide-react';
import MovieRow from '../components/MovieRow';

const MOODS = [
  { id: 'chill', label: 'Chill' },
  { id: 'laugh', label: 'Laugh' },
  { id: 'thrill', label: 'Thrill' },
  { id: 'romance', label: 'Romance' },
  { id: 'action', label: 'Action' },
  { id: 'family', label: 'Family' },
  { id: 'scifi', label: 'Sci‑Fi' },
  { id: 'fantasy', label: 'Fantasy' },
  { id: 'mystery', label: 'Mystery' },
];

/** Guest / fallback: primary TMDB genre id per mood (matches backend MOOD_GENRES) */
const MOOD_DISCOVER_GENRE = {
  chill: '18',
  laugh: '35',
  thrill: '53',
  romance: '10749',
  action: '28',
  family: '10751',
  scifi: '878',
  fantasy: '14',
  mystery: '9648',
};

const Home = () => {
  const [heroMovies, setHeroMovies] = useState([]);
  const [heroIdx, setHeroIdx] = useState(0);
  const [trending, setTrending] = useState([]);
  const [popular, setPopular] = useState([]);
  const [topRated, setTopRated] = useState([]);
  const [nowPlaying, setNowPlaying] = useState([]);
  const [upcoming, setUpcoming] = useState([]);
  const [recHybrid, setRecHybrid] = useState([]);
  const [recContent, setRecContent] = useState([]);
  const [recCollab, setRecCollab] = useState([]);
  const [selectedMood, setSelectedMood] = useState(null);
  const [moodMovies, setMoodMovies] = useState([]);
  const { user } = useAuth();

  useEffect(() => {
    loadMovies();
  }, [user]);

  const loadMovies = async () => {
    try {
      const [trendingRes, popularRes, topRatedRes, nowPlayingRes, upcomingRes] = await Promise.all([
        movieApi.getTrending(),
        movieApi.getPopular(),
        movieApi.getTopRated(),
        movieApi.getNowPlaying(),
        movieApi.getUpcoming(),
      ]);
      const t = trendingRes.data.results || [];
      setTrending(t);
      setHeroMovies(t.slice(0, 5).filter(m => m.backdrop_path));
      setPopular(popularRes.data.results || []);
      setTopRated(topRatedRes.data.results || []);
      setNowPlaying(nowPlayingRes.data.results || []);
      setUpcoming(upcomingRes.data.results || []);

      if (user) {
        try {
          const [hybridRes, contentRes, collabRes] = await Promise.all([
            movieApi.getRecommendations({ type: 'hybrid' }),
            movieApi.getRecommendations({ type: 'content' }),
            movieApi.getRecommendations({ type: 'collaborative' }),
          ]);
          setRecHybrid(hybridRes.data.results || []);
          setRecContent(contentRes.data.results || []);
          setRecCollab(collabRes.data.results || []);
        } catch (e) {
          setRecHybrid([]);
          setRecContent([]);
          setRecCollab([]);
        }
      } else {
        setRecHybrid([]);
        setRecContent([]);
        setRecCollab([]);
        setMoodMovies([]);
      }
    } catch (error) {
      console.error('Error loading movies:', error);
    }
  };

  const nextHero = useCallback(() => setHeroIdx(i => (i + 1) % heroMovies.length), [heroMovies.length]);
  const prevHero = useCallback(() => setHeroIdx(i => (i - 1 + heroMovies.length) % heroMovies.length), [heroMovies.length]);

  useEffect(() => {
    if (heroMovies.length === 0) return;
    const timer = setInterval(nextHero, 7000);
    return () => clearInterval(timer);
  }, [heroMovies.length, nextHero]);

  useEffect(() => {
    if (!selectedMood) {
      setMoodMovies([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        if (user) {
          const res = await movieApi.getRecommendations({ type: 'mood', mood: selectedMood });
          if (!cancelled) setMoodMovies(res.data.results || []);
        } else {
          const gid = MOOD_DISCOVER_GENRE[selectedMood];
          if (!gid) {
            if (!cancelled) setMoodMovies([]);
            return;
          }
          const res = await movieApi.discover({ genre: gid });
          if (!cancelled) setMoodMovies(res.data.results || []);
        }
      } catch {
        if (!cancelled) setMoodMovies([]);
      }
    })();
    return () => { cancelled = true; };
  }, [user, selectedMood]);

  const hero = heroMovies[heroIdx];

  return (
    <div className="min-h-screen bg-black pt-14" data-testid="home-page">
      {hero && (
        <div className="relative h-[75vh] md:h-[85vh] w-full overflow-hidden group" data-testid="hero-banner">
          {heroMovies.map((m, idx) => (
            <div
              key={m.id}
              className="absolute inset-0 transition-opacity duration-1000"
              style={{ opacity: idx === heroIdx ? 1 : 0 }}
            >
              <img
                src={`https://image.tmdb.org/t/p/original${m.backdrop_path}`}
                alt={m.title}
                className="w-full h-full object-cover"
              />
            </div>
          ))}

          <div className="atv-hero-gradient absolute inset-0" />

          <button
            onClick={prevHero}
            className="absolute left-4 top-1/2 -translate-y-1/2 z-10 w-10 h-10 rounded-full bg-black/40 backdrop-blur-md flex items-center justify-center text-white/80 hover:text-white opacity-0 group-hover:opacity-100 transition-opacity"
            data-testid="hero-prev"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
          <button
            onClick={nextHero}
            className="absolute right-4 top-1/2 -translate-y-1/2 z-10 w-10 h-10 rounded-full bg-black/40 backdrop-blur-md flex items-center justify-center text-white/80 hover:text-white opacity-0 group-hover:opacity-100 transition-opacity"
            data-testid="hero-next"
          >
            <ChevronRight className="w-5 h-5" />
          </button>

          <div className="absolute bottom-0 left-0 right-0 px-6 md:px-12 lg:px-14 pb-16 md:pb-20 z-10">
            <div className="max-w-2xl atv-animate-in" key={hero.id}>
              <div className="flex items-center gap-3 mb-3">
                <span className="text-xs font-medium tracking-wider text-[#86868B] uppercase">
                  {hero.release_date?.split('-')[0]}
                </span>
                <span className="w-1 h-1 rounded-full bg-[#48484A]" />
                <span className="text-xs font-medium text-[#86868B] uppercase tracking-wider">
                  {hero.vote_average?.toFixed(1)} Rating
                </span>
              </div>

              <h1
                className="text-4xl sm:text-5xl lg:text-6xl font-black tracking-tight leading-[1.05] text-white mb-4"
                style={{ fontFamily: 'Inter, sans-serif' }}
                data-testid="hero-title"
              >
                {hero.title}
              </h1>

              <p className="text-base md:text-lg leading-relaxed text-[#A1A1A6] mb-8 line-clamp-2 max-w-xl">
                {hero.overview}
              </p>

              <div className="flex items-center gap-3">
                <Link
                  to={`/movie/${hero.id}`}
                  className="atv-btn-primary inline-flex items-center gap-2 rounded-full px-7 py-3 text-sm"
                  data-testid="hero-play-button"
                >
                  <Play className="w-4 h-4 fill-current" />
                  Watch Now
                </Link>
                <Link
                  to={`/movie/${hero.id}`}
                  className="atv-btn-secondary inline-flex items-center gap-2 rounded-full px-7 py-3 text-sm border border-white/[0.08]"
                  data-testid="hero-info-button"
                >
                  <Plus className="w-4 h-4" />
                  More Info
                </Link>
              </div>
            </div>

            <div className="flex items-center gap-2 mt-8">
              {heroMovies.map((_, idx) => (
                <button
                  key={idx}
                  onClick={() => setHeroIdx(idx)}
                  className={`transition-all duration-300 rounded-full ${
                    idx === heroIdx ? 'w-8 h-1.5 bg-white' : 'w-1.5 h-1.5 bg-white/30 hover:bg-white/50'
                  }`}
                  data-testid={`hero-dot-${idx}`}
                />
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="py-10 space-y-10">
        <section className="px-6 md:px-12 lg:px-14 mb-2" data-testid="mood-strip">
          <h2
            className="text-xl md:text-2xl font-bold tracking-tight text-[#F5F5F7] mb-4"
            style={{ fontFamily: 'Inter, sans-serif' }}
          >
            What are you in the mood for?
          </h2>
          <div className="flex gap-2 md:gap-3 overflow-x-auto scrollbar-hide atv-row-scroll pb-1">
            {MOODS.map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => setSelectedMood((prev) => (prev === m.id ? null : m.id))}
                className={`atv-mood-chip flex-shrink-0 rounded-full px-5 py-2.5 text-sm font-medium transition-all ${
                  selectedMood === m.id ? 'atv-mood-chip-active' : ''
                }`}
                data-testid={`mood-${m.id}`}
              >
                {m.label}
              </button>
            ))}
          </div>
        </section>

        {trending.length > 0 && <MovieRow title="Trending Now" movies={trending} large />}
        {user && recHybrid.length > 0 && (
          <MovieRow title="For You" subtitle="Hybrid picks — taste + community" movies={recHybrid} />
        )}
        {user && recContent.length > 0 && (
          <MovieRow title="Because of Your Taste" subtitle="TF‑IDF on plots & genres · cosine match" movies={recContent} />
        )}
        {user && recCollab.length > 0 && (
          <MovieRow title="Fans Like You" subtitle="Collaborative filtering across ratings" movies={recCollab} />
        )}
        {selectedMood && moodMovies.length > 0 && (
          <MovieRow
            title={`${MOODS.find((x) => x.id === selectedMood)?.label || 'Your mood'} picks`}
            subtitle={
              user
                ? 'Blended with your profile'
                : 'Popular titles in this vibe — sign in for personalized picks'
            }
            movies={moodMovies}
          />
        )}
        {popular.length > 0 && <MovieRow title="Popular" movies={popular} />}
        {topRated.length > 0 && <MovieRow title="Top Rated" movies={topRated} />}
        {nowPlaying.length > 0 && <MovieRow title="Now Playing" movies={nowPlaying} />}
        {upcoming.length > 0 && <MovieRow title="Coming Soon" movies={upcoming} />}
      </div>
    </div>
  );
};

export default Home;
