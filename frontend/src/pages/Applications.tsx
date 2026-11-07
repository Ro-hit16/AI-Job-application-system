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

const TAILOR_ERROR_PREFIX = "Resume tailoring failed";
type ResumeState = "ready" | "failed" | "missing";
const getResumeState = (app: any): ResumeState => {
  if (app.tailored_resume_path) return "ready";
  if (
    typeof app.error_message === "string" &&
    app.error_message.startsWith(TAILOR_ERROR_PREFIX)
  )
    return "failed";
  return "missing";
};

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
  needs_manual_review: {
    bg: "bg-amber-100",
    text: "text-amber-800",
    icon: UserCogIcon,
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
      // Determine extension from the server's Content-Type header so we
      // always get .pdf even if the stored path ended in .tex.
      const ct = String(res.headers?.["content-type"] ?? "");
      const ext = ct.includes("pdf") ? "pdf" : ct.includes("tex") ? "tex" : "pdf";
      const blob = new Blob([res.data], { type: ct || "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;

      let downloadName = "";
      const disposition: string = res.headers?.["content-disposition"] ?? "";
      if (disposition && disposition.includes("filename=")) {
        const match = disposition.match(/filename=["']?([^"';]+)["']?/);
        if (match && match[1]) {
          downloadName = match[1];
        }
      }
      if (!downloadName) {
        const targetApp = apps.find((app) => app.id === id);
        const companyClean = targetApp?.job?.company
          ? targetApp.job.company.replace(/[^\w\s-]/g, "").trim().replace(/\s+/g, "_")
          : "";
        downloadName = companyClean
          ? `Rohit_Devkar_Resume_${companyClean}.${ext}`
          : `Rohit_Devkar_Resume.${ext}`;
      }

      a.download = downloadName;
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
        {["", "pending_approval", "needs_manual_review", "submitted", "rejected", "failed"].map(
          (s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-sm capitalize transition-colors ${statusFilter === s
                ? "bg-blue-600 text-white"
                : "bg-white border border-gray-200 text-gray-600 hover:bg-gray-50"
                }`}
            >
              {s === "" ? "All" : s.replace(/_/g, " ")}
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
            const resumeState = getResumeState(app);
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
                        {app.status.replace(/_/g, " ")}
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
                    {resumeState === "ready" && (
                      <p className="text-xs text-green-600 mt-1">
                        Tailored resume ready
                      </p>
                    )}
                    {resumeState === "failed" && (
                      <p className="text-xs text-red-600 mt-1">
                        Resume generation failed — no file to download. Apply
                        manually or re-run tailoring.
                      </p>
                    )}
                    {resumeState === "missing" && (
                      <p className="text-xs text-gray-400 mt-1">
                        No tailored resume generated yet
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
                  <button
                    onClick={() => handleDownloadResume(app.id)}
                    disabled={resumeState !== "ready"}
                    title={
                      resumeState === "ready"
                        ? "Download tailored PDF resume"
                        : resumeState === "failed"
                          ? "Resume generation failed — re-run the agent to regenerate"
                          : "Resume has not been generated yet"
                    }
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border transition-colors ${resumeState === "ready"
                      ? "bg-white border-gray-200 text-gray-700 hover:bg-gray-100 cursor-pointer"
                      : "bg-gray-50 border-gray-200 text-gray-400 cursor-not-allowed"
                      }`}
                  >
                    <DownloadIcon className="w-3.5 h-3.5" />
                    {resumeState === "ready"
                      ? "Download Resume (PDF)"
                      : resumeState === "failed"
                        ? "Resume failed"
                        : "Resume not generated"}
                  </button>
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

                {(interveneId === app.id ||
                  app.status === "needs_manual_review") && (
                    <div className="mt-3 p-4 bg-amber-50 border border-amber-200 rounded-lg text-sm">
                      <p className="font-medium text-amber-800 mb-1">
                        {app.status === "needs_manual_review"
                          ? "Auto-apply stopped — needs manual review"
                          : "Manual review"}
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
                        {resumeState === "ready" && (
                          <button
                            onClick={() => handleDownloadResume(app.id)}
                            className="flex items-center gap-1.5 bg-white border border-amber-300 text-amber-800 px-3 py-1.5 rounded-lg text-xs hover:bg-amber-100"
                          >
                            <DownloadIcon className="w-3.5 h-3.5" /> Download Resume (PDF)
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