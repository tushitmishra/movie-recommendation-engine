import { Link } from 'react-router-dom';
import { useRef, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

const MovieRow = ({ title, subtitle, movies, large = false }) => {
  const scrollRef = useRef(null);
  const [showLeft, setShowLeft] = useState(false);
  const [showRight, setShowRight] = useState(true);

  const scroll = (direction) => {
    const container = scrollRef.current;
    if (!container) return;
    const amount = container.clientWidth * 0.75;
    container.scrollBy({ left: direction === 'left' ? -amount : amount, behavior: 'smooth' });
  };

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    setShowLeft(el.scrollLeft > 20);
    setShowRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 20);
  };

  const cardWidth = large ? 'w-[280px] md:w-[340px]' : 'w-[160px] md:w-[185px]';
  const aspect = large ? 'aspect-[16/9]' : 'aspect-[2/3]';

  return (
    <div className="relative group/row" data-testid="movie-row">
      <div className="flex items-baseline justify-between mb-3 px-6 md:px-12 lg:px-14">
        <div>
          <h2
            className="text-xl md:text-2xl font-bold tracking-tight text-[#F5F5F7]"
            style={{ fontFamily: 'Inter, sans-serif' }}
          >
            {title}
          </h2>
          {subtitle && (
            <p className="text-xs md:text-sm text-[#86868B] mt-1 font-normal tracking-wide">{subtitle}</p>
          )}
        </div>
        <span className="text-sm text-[#0071E3] hover:underline cursor-pointer hidden md:block">
          See All
        </span>
      </div>

      <div className="relative">
        {showLeft && (
          <button
            onClick={() => scroll('left')}
            className="absolute left-1 top-1/2 -translate-y-1/2 z-10 w-10 h-10 rounded-full bg-black/60 backdrop-blur-md flex items-center justify-center text-white opacity-0 group-hover/row:opacity-100 transition-opacity"
            data-testid="scroll-left"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
        )}

        <div
          ref={scrollRef}
          onScroll={onScroll}
          className="flex gap-3 md:gap-4 overflow-x-auto scrollbar-hide atv-row-scroll px-6 md:px-12 lg:px-14 pb-2"
        >
          {movies.map((movie) => (
            <Link
              key={movie.id}
              to={`/movie/${movie.id}`}
              className={`atv-card flex-shrink-0 ${cardWidth} rounded-lg overflow-hidden relative`}
              data-testid={`movie-card-${movie.id}`}
            >
              <div className={`${aspect} relative overflow-hidden rounded-lg bg-[#1D1D1F]`}>
                {movie.poster_path || movie.backdrop_path ? (
                  <img
                    src={`https://image.tmdb.org/t/p/w500${large ? (movie.backdrop_path || movie.poster_path) : (movie.poster_path || movie.backdrop_path)}`}
                    alt={movie.title}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-[#48484A] text-xs">
                    No Image
                  </div>
                )}

                {large && (
                  <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent flex items-end p-5">
                    <div>
                      <h3 className="text-lg font-bold text-white leading-tight">{movie.title}</h3>
                      <p className="text-xs text-white/60 mt-1">{movie.release_date?.split('-')[0]}</p>
                    </div>
                  </div>
                )}
              </div>

              {!large && (
                <div className="mt-2 px-0.5">
                  <h3 className="text-[13px] font-medium text-[#F5F5F7] line-clamp-1 leading-tight">{movie.title}</h3>
                  <p className="text-[11px] text-[#86868B] mt-0.5">{movie.release_date?.split('-')[0]}</p>
                </div>
              )}
            </Link>
          ))}
        </div>

        {showRight && (
          <button
            onClick={() => scroll('right')}
            className="absolute right-1 top-1/2 -translate-y-1/2 z-10 w-10 h-10 rounded-full bg-black/60 backdrop-blur-md flex items-center justify-center text-white opacity-0 group-hover/row:opacity-100 transition-opacity"
            data-testid="scroll-right"
          >
            <ChevronRight className="w-5 h-5" />
          </button>
        )}
      </div>
    </div>
  );
};

export default MovieRow;
