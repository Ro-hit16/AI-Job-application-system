// src/pages/Applications.tsx
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { applicationsApi, extractErrorDetail } from "../api/client";
import {
  CheckCircleIcon,
  XCircleIcon,
  ClockIcon,
  AlertCircleIcon,
  DownloadIcon,
  UserCogIcon,
} from "lucide-react";

const STATUS_STYLES: Record<
  string,
  { bg: string; text: string; icon: React.ElementType }
> = {
  pending_approval: {
    bg: "bg-amber-100",
    text: "text-amber-700",
    icon: ClockIcon,
  },
  approved: { bg: "bg-blue-100", text: "text-blue-700", icon: CheckCircleIcon },
  submitted: {
    bg: "bg-green-100",
    text: "text-green-700",
    icon: CheckCircleIcon,
  },
  rejected: { bg: "bg-red-100", text: "text-red-700", icon: XCircleIcon },
  failed: { bg: "bg-red-100", text: "text-red-700", icon: AlertCircleIcon },
};

export default function Applications() {
  const [statusFilter, setStatusFilter] = useState("");
  const [interveneId, setInterveneId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["applications", statusFilter],
    queryFn: () => applicationsApi.list(statusFilter || undefined),
    refetchInterval: 30000,
  });

  const markManualMutation = useMutation({
    mutationFn: (id: string) => applicationsApi.markManuallyApplied(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      setInterveneId(null);
    },
  });

  const apps: any[] = data?.data ?? [];

  const handleDownloadResume = async (id: string) => {
    try {
      const res = await applicationsApi.downloadResume(id);
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = `updated_resume_${id}.txt`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      alert(
        await extractErrorDetail(err, "Could not download the updated resume."),
      );
    }
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Applications</h1>

      <div className="flex gap-2 mb-6">
        {["", "pending_approval", "submitted", "rejected", "failed"].map(
          (s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-sm capitalize transition-colors ${
                statusFilter === s
                  ? "bg-blue-600 text-white"
                  : "bg-white border border-gray-200 text-gray-600 hover:bg-gray-50"
              }`}
            >
              {s === "" ? "All" : s.replace("_", " ")}
            </button>
          ),
        )}
      </div>

      {isLoading ? (
        <div className="text-center py-12 text-gray-500">Loading...</div>
      ) : apps.length === 0 ? (
        <div className="text-center py-12 text-gray-400 bg-white rounded-xl border border-gray-200">
          No applications yet. Run the agent pipeline to start applying.
        </div>
      ) : (
        <div className="space-y-3">
          {apps.map((app) => {
            const style =
              STATUS_STYLES[app.status] ?? STATUS_STYLES["pending_approval"];
            const Icon = style.icon;
            return (
              <div
                key={app.id}
                className="bg-white rounded-xl border border-gray-200 p-5"
              >
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium ${style.bg} ${style.text}`}
                      >
                        <Icon className="w-3 h-3" />
                        {app.status.replace("_", " ")}
                      </span>
                      {app.match_score && (
                        <span className="text-xs text-gray-500">
                          Match:{" "}
                          <span className="font-semibold text-blue-600">
                            {app.match_score.toFixed(1)}%
                          </span>
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-gray-500 font-mono text-xs">
                      ID: {app.id.slice(0, 16)}…
                    </p>
                    {app.confirmation_number && (
                      <p className="text-sm text-green-600 mt-1">
                        Confirmation:{" "}
                        <span className="font-medium">
                          {app.confirmation_number}
                        </span>
                      </p>
                    )}
                    {app.error_message && (
                      <p className="text-sm text-red-500 mt-1">
                        {app.error_message}
                      </p>
                    )}
                    {app.tailored_resume_path && (
                      <p className="text-xs text-gray-400 mt-1 truncate">
                        Resume: {app.tailored_resume_path}
                      </p>
                    )}
                  </div>
                  <div className="text-right ml-4">
                    <p className="text-xs text-gray-400">
                      {new Date(app.created_at).toLocaleDateString()}
                    </p>
                    {app.applied_at && (
                      <p className="text-xs text-green-500 mt-0.5">
                        Applied {new Date(app.applied_at).toLocaleDateString()}
                      </p>
                    )}
                  </div>
                </div>

                <div className="flex gap-2 mt-3">
                  {app.tailored_resume_path && (
                    <button
                      onClick={() => handleDownloadResume(app.id)}
                      className="flex items-center gap-1.5 bg-white border border-gray-200 text-gray-700 px-3 py-1.5 rounded-lg text-xs hover:bg-gray-100"
                    >
                      <DownloadIcon className="w-3.5 h-3.5" /> Download Updated
                      Resume
                    </button>
                  )}
                  {app.status !== "submitted" && app.status !== "rejected" && (
                    <button
                      onClick={() =>
                        setInterveneId(interveneId === app.id ? null : app.id)
                      }
                      className="flex items-center gap-1.5 bg-white border border-gray-200 text-gray-700 px-3 py-1.5 rounded-lg text-xs hover:bg-gray-100"
                    >
                      <UserCogIcon className="w-3.5 h-3.5" />
                      {interveneId === app.id ? "Close" : "Manual Intervention"}
                    </button>
                  )}
                </div>

                {interveneId === app.id && (
                  <div className="mt-3 p-4 bg-amber-50 border border-amber-200 rounded-lg text-sm">
                    <p className="font-medium text-amber-800 mb-1">
                      Manual review
                    </p>
                    <p className="text-amber-700 mb-2">
                      {app.error_message ||
                        "This application needs your attention. Review it and apply manually if needed — nothing is submitted automatically from here."}
                    </p>

                    {app.job?.url && (
                      <a
                        href={app.job.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-blue-600 hover:underline text-xs inline-block mb-2"
                      >
                        Open job posting to apply manually ↗
                      </a>
                    )}

                    <div className="flex gap-2 mt-2">
                      {app.tailored_resume_path && (
                        <button
                          onClick={() => handleDownloadResume(app.id)}
                          className="flex items-center gap-1.5 bg-white border border-amber-300 text-amber-800 px-3 py-1.5 rounded-lg text-xs hover:bg-amber-100"
                        >
                          <DownloadIcon className="w-3.5 h-3.5" /> Download
                          Updated Resume
                        </button>
                      )}
                      <button
                        onClick={() => markManualMutation.mutate(app.id)}
                        disabled={markManualMutation.isPending}
                        className="flex items-center gap-1.5 bg-amber-600 text-white px-3 py-1.5 rounded-lg text-xs hover:bg-amber-700 disabled:opacity-50"
                      >
                        <CheckCircleIcon className="w-3.5 h-3.5" />
                        I've applied manually — mark as submitted
                      </button>
                    </div>
                    <p className="text-xs text-amber-600 mt-2">
                      This only records that you applied yourself on the portal
                      — it does not trigger any automatic submission.
                    </p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
