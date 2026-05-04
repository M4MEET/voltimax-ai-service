import { useEffect, useState } from 'react';
import { Doughnut } from 'react-chartjs-2';
import { ThumbsUp, ThumbsDown } from 'lucide-react';
import { apiFetch } from '../api';
import { usePeriod } from '../hooks/usePeriod';
import type { FeedbackData, RatingsData } from '../types';
import KpiCard from '../components/KpiCard';
import { CardSkeleton, ChartSkeleton } from '../components/Skeleton';

export default function Feedback() {
  const { days } = usePeriod();
  const [feedback, setFeedback] = useState<FeedbackData | null>(null);
  const [ratings, setRatings] = useState<RatingsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    setError('');
    Promise.all([
      apiFetch<FeedbackData>(`/api/analytics/feedback?days=${days}`),
      apiFetch<RatingsData>(`/api/analytics/ratings?days=${days}`),
    ])
      .then(([f, r]) => {
        setFeedback(f);
        setRatings(r);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [days]);

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-red-700 animate-fade-in">
        Failed to load data: {error}
      </div>
    );
  }

  if (loading || !feedback || !ratings) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ChartSkeleton />
          <ChartSkeleton />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <h1 className="text-xl font-bold text-gray-900">Feedback &amp; Ratings</h1>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Satisfaction Rate" value={`${(feedback.satisfaction_rate * 100).toFixed(1)}%`} color="green" index={0} sub={`${feedback.total} votes`} />
        <KpiCard label="Thumbs Up" value={feedback.up} color="green" index={1} />
        <KpiCard label="Thumbs Down" value={feedback.down} color="red" index={2} />
        <KpiCard label="Avg Rating" value={`${ratings.avg_rating.toFixed(1)} / 5`} color="purple" index={3} sub={`${ratings.total} ratings`} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Thumbs breakdown */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-card-pop stagger-1">
          <h2 className="text-sm font-semibold text-gray-900 mb-6">Thumbs Breakdown</h2>
          <div className="flex items-center justify-center">
            <Doughnut
              data={{
                labels: ['Positive', 'Negative'],
                datasets: [
                  {
                    data: [feedback.up, feedback.down],
                    backgroundColor: ['#10b981', '#ef4444'],
                    borderWidth: 0,
                    spacing: 4,
                    borderRadius: 4,
                  },
                ],
              }}
              options={{
                responsive: true,
                cutout: '70%',
                plugins: {
                  legend: { position: 'bottom', labels: { padding: 20 } },
                },
              }}
            />
          </div>
          <div className="flex items-center justify-center gap-8 mt-4">
            <div className="flex items-center gap-2 text-emerald-600">
              <ThumbsUp size={16} />
              <span className="text-sm font-semibold">{feedback.up}</span>
            </div>
            <div className="flex items-center gap-2 text-red-500">
              <ThumbsDown size={16} />
              <span className="text-sm font-semibold">{feedback.down}</span>
            </div>
          </div>
        </div>

        {/* Ratings distribution */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 animate-card-pop stagger-2">
          <h2 className="text-sm font-semibold text-gray-900 mb-6">Rating Distribution</h2>
          <div className="space-y-3">
            {['5', '4', '3', '2', '1'].map((star) => {
              const count = ratings.distribution[star] ?? 0;
              const pct = ratings.total > 0 ? (count / ratings.total) * 100 : 0;
              return (
                <div key={star} className="flex items-center gap-3">
                  <span className="text-sm font-medium text-gray-600 w-12">{star} star</span>
                  <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full transition-all duration-500"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-xs text-gray-400 w-10 text-right">{count}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
