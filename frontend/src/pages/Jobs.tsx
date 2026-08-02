// src/pages/Jobs.tsx
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { jobsApi } from "../api/client";
import { SearchIcon, ExternalLinkIcon } from "lucide-react";

export default function Jobs() {
  const [search, setSearch] = useState("");
  const [portal, setPortal] = useState("");
  const [status, setStatus] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["jobs", search, portal, status],
    queryFn: () => jobsApi.list({ search: search || undefined, portal: portal || undefined, status: status || undefined, limit: 50 }),
    staleTime: 30000,
  });

  const jobs: any[] = data?.data ?? [];

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Job Listings</h1>

      <div className="flex gap-3 mb-6 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <SearchIcon className="absolute left-3 top-2.5 w-4 h-4 text-gray-400" />
          <input
            className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Search jobs..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <select
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={portal}
          onChange={(e) => setPortal(e.target.value)}
        >
          <option value="">All Portals</option>
          <option value="linkedin">LinkedIn</option>
          <option value="indeed">Indeed</option>
          <option value="naukri">Naukri</option>
        </select>

        <select
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">All Status</option>
          <option value="new">New</option>
          <option value="matched">Matched</option>
          <option value="applied">Applied</option>
        </select>
      </div>

      {isLoading ? (
        <div className="text-center py-12 text-gray-500">
          Loading jobs...
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map((job: any) => (
            <div
              key={job.id}
              className="bg-white rounded-xl border border-gray-200 p-5 hover:border-blue-200 transition-colors"
            >
              <div className="flex justify-between items-start">
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-gray-900">
                    {job.title}
                  </h3>

                  <p className="text-sm text-gray-600 mt-0.5">
                    {job.company} · {job.location}
                  </p>

                  <div className="flex gap-2 mt-2 flex-wrap">
                    <span className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full">
                      {job.portal}
                    </span>

                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ${
                        job.status === "applied"
                          ? "bg-green-100 text-green-700"
                          : job.status === "matched"
                          ? "bg-blue-100 text-blue-700"
                          : "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {job.status}
                    </span>

                    {job.salary && (
                      <span className="text-xs bg-green-50 text-green-700 px-2 py-0.5 rounded-full">
                        {job.salary}
                      </span>
                    )}

                    {job.experience_required && (
                      <span className="text-xs bg-purple-50 text-purple-700 px-2 py-0.5 rounded-full">
                        {job.experience_required}
                      </span>
                    )}
                  </div>

                  <p
                    className="text-sm text-gray-500 mt-2"
                    style={{
                      display: "-webkit-box",
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                    }}
                  >
                    {job.description}
                  </p>
                </div>

                <a
                  href={job.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ml-4 text-gray-400 hover:text-blue-500 flex-shrink-0"
                >
                  <ExternalLinkIcon className="w-4 h-4" />
                </a>
              </div>
            </div>
          ))}

          {jobs.length === 0 && (
            <div className="text-center py-12 text-gray-400 bg-white rounded-xl border border-gray-200">
              No jobs found. Try adjusting filters or running the pipeline.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
