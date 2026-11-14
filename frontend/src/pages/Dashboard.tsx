// src/pages/Dashboard.tsx
import { useQuery } from "@tanstack/react-query";
import { applicationsApi, jobsApi, notificationsApi } from "../api/client";
import { BriefcaseIcon, CheckCircleIcon, BellIcon, TrendingUpIcon } from "lucide-react";

export default function Dashboard() {
  const { data: jobs } = useQuery({ queryKey: ["jobs"], queryFn: () => jobsApi.list({ limit: 100 }) });
  const { data: apps } = useQuery({ queryKey: ["applications"], queryFn: () => applicationsApi.list() });
  const { data: pending } = useQuery({ queryKey: ["pending"], queryFn: () => applicationsApi.pending() });
  const { data: notifs } = useQuery({ queryKey: ["notifs"], queryFn: () => notificationsApi.list(true) });

  const stats = [
    { label: "Jobs Found", value: jobs?.data?.length ?? 0, icon: BriefcaseIcon, color: "text-blue-500" },
    { label: "Applications", value: apps?.data?.length ?? 0, icon: TrendingUpIcon, color: "text-green-500" },
    { label: "Pending Approval", value: pending?.data?.length ?? 0, icon: CheckCircleIcon, color: "text-amber-500" },
    { label: "Notifications", value: notifs?.data?.length ?? 0, icon: BellIcon, color: "text-purple-500" },
  ];

  return (
    <div className="p-4 sm:p-6">
      <h1 className="text-xl sm:text-2xl font-bold text-gray-900 mb-4 sm:mb-6">Dashboard</h1>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6 sm:mb-8">
        {stats.map((s) => (
          <div key={s.label} className="bg-white rounded-xl border border-gray-200 p-4 sm:p-5 flex items-center gap-3 sm:gap-4">
            <s.icon className={`w-6 h-6 sm:w-8 sm:h-8 ${s.color} shrink-0`} />
            <div className="min-w-0">
              <p className="text-xl sm:text-2xl font-bold text-gray-900">{s.value}</p>
              <p className="text-xs sm:text-sm text-gray-500 leading-tight">{s.label}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-5">
        <h2 className="font-semibold text-gray-800 mb-3 text-sm sm:text-base">Recent Jobs</h2>
        <div className="divide-y divide-gray-100">
          {(jobs?.data ?? []).slice(0, 5).map((job: any) => (
            <div key={job.id} className="py-3 flex justify-between items-center gap-2">
              <div className="min-w-0 flex-1">
                <p className="font-medium text-gray-900 text-sm truncate">{job.title}</p>
                <p className="text-xs text-gray-500 truncate">{job.company} · {job.portal}</p>
              </div>
              <span className={`text-xs px-2 py-1 rounded-full shrink-0 ${job.status === "applied" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"}`}>
                {job.status}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
