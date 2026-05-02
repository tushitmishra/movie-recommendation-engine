import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API_BASE = `${BACKEND_URL}/api`;

const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
});

export const movieApi = {
  getTrending: () => api.get('/movies/trending'),
  getPopular: () => api.get('/movies/popular'),
  getTopRated: () => api.get('/movies/top-rated'),
  getNowPlaying: () => api.get('/movies/now-playing'),
  getUpcoming: () => api.get('/movies/upcoming'),
  getDetails: (id) => api.get(`/movies/${id}`),
  search: (query, page = 1) => api.get('/movies/search', { params: { query, page } }),
  discover: (params) => api.get('/movies/discover', { params }),
  getGenres: () => api.get('/genres'),
  getRecommendations: (params = {}) => api.get('/recommendations', { params }),
};

export const watchlistApi = {
  get: () => api.get('/watchlist'),
  add: (movieId) => api.post(`/watchlist/${movieId}`),
  remove: (movieId) => api.delete(`/watchlist/${movieId}`),
};

export const favoritesApi = {
  add: (movieId) => api.post(`/favorites/${movieId}`),
  remove: (movieId) => api.delete(`/favorites/${movieId}`),
};

export const ratingsApi = {
  create: (data) => api.post('/ratings', data),
  getForMovie: (movieId) => api.get(`/ratings/movie/${movieId}`),
};

export default api;