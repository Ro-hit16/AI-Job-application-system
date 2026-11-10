// src/pages/Applications.tsx
import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { applicationsApi, extractErrorDetail } from "../api/client";
import { useAuthStore } from "../store/auth";
import {
  CheckCircleIcon,
  XCircleIcon,
  ClockIcon,
  AlertCircleIcon,
  DownloadIcon,
  UserCogIcon,
  ExternalLinkIcon,
  SparklesIcon,
  FilterIcon,
  ZapIcon,
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

const MATCH_SCORE_RANGES = [
  { label: "All Match Scores", value: "all" },
  { label: "95%+ Match", value: "95+" },
  { label: "90% - 95%", value: "90-95" },
  { label: "85% - 90%", value: "85-90" },
  { label: "70% - 85%", value: "70-85" },
  { label: "50% - 70%", value: "50-70" },
];

export default function Applications() {
  const [statusFilter, setStatusFilter] = useState("");
  const [matchFilter, setMatchFilter] = useState("all");
  const [interveneId, setInterveneId] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const { user } = useAuthStore();

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

  const rawApps: any[] = data?.data ?? [];

  // Filter applications by match score range
  const filteredApps = useMemo(() => {
    return rawApps.filter((app) => {
      const score = app.match_score ?? 0;
      switch (matchFilter) {
        case "95+":
          return score >= 95.0;
        case "90-95":
          return score >= 90.0 && score < 95.0;
        case "85-90":
          return score >= 85.0 && score < 90.0;
        case "70-85":
          return score >= 70.0 && score < 85.0;
        case "50-70":
          return score >= 50.0 && score < 70.0;
        default:
          return true;
      }
    });
  }, [rawApps, matchFilter]);

  const handleDownloadResume = async (id: string) => {
    try {
      const res = await applicationsApi.downloadResume(id);
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
        const targetApp = rawApps.find((app) => app.id === id);
        const companyClean = targetApp?.job?.company
          ? targetApp.job.company.replace(/[^\w\s-]/g, "").trim().replace(/\s+/g, "_")
          : "";
        const candidateName = user?.full_name
          ? user.full_name.replace(/[^\w\s-]/g, "").trim().replace(/\s+/g, "_")
          : "Resume";
        downloadName = companyClean
          ? `${candidateName}_Resume_${companyClean}.${ext}`
          : `${candidateName}_Resume.${ext}`;
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

  const getScoreBadgeColor = (score: number) => {
    if (score >= 90) return "bg-emerald-50 text-emerald-700 border-emerald-200";
    if (score >= 85) return "bg-blue-50 text-blue-700 border-blue-200";
    if (score >= 70) return "bg-indigo-50 text-indigo-700 border-indigo-200";
    return "bg-amber-50 text-amber-700 border-amber-200";
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Applications</h1>
          <p className="text-sm text-gray-500 mt-1">
            Tracking {filteredApps.length} of {rawApps.length} total applications
          </p>
        </div>

        {/* Match Score Filter Dropdown */}
        <div className="flex items-center gap-2">
          <FilterIcon className="w-4 h-4 text-gray-400" />
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            Match:
          </span>
          <select
            value={matchFilter}
            onChange={(e) => setMatchFilter(e.target.value)}
            className="border border-gray-200 bg-white rounded-lg px-3 py-1.5 text-sm font-medium text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer shadow-sm"
          >
            {MATCH_SCORE_RANGES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Status Filter Tabs */}
      <div className="flex gap-2 mb-6 overflow-x-auto pb-1">
        {["", "pending_approval", "needs_manual_review", "submitted", "approved", "rejected", "failed"].map(
          (s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-sm capitalize whitespace-nowrap transition-colors ${
                statusFilter === s
                  ? "bg-blue-600 text-white font-medium shadow-sm"
                  : "bg-white border border-gray-200 text-gray-600 hover:bg-gray-50"
              }`}
            >
              {s === "" ? "All Statuses" : s.replace(/_/g, " ")}
            </button>
          ),
        )}
      </div>

      {isLoading ? (
        <div className="text-center py-16 text-gray-500">Loading applications...</div>
      ) : filteredApps.length === 0 ? (
        <div className="text-center py-16 text-gray-400 bg-white rounded-xl border border-gray-200 shadow-sm">
          No applications match your filter criteria.
        </div>
      ) : (
        <div className="space-y-4">
          {filteredApps.map((app) => {
            const style =
              STATUS_STYLES[app.status] ?? STATUS_STYLES["pending_approval"];
            const Icon = style.icon;
            const resumeState = getResumeState(app);
            const score = app.match_score ?? 0;
            const isAutoApply = score >= 85.0;

            const jobTitle = app.job?.title || "Software Developer";
            const companyName = app.job?.company || "Tech Company";
            const location = app.job?.location || "Remote";
            const portal = app.job?.portal || "job board";
            const jobUrl = app.job?.url;

            return (
              <div
                key={app.id}
                className="bg-white rounded-xl border border-gray-200 p-5 hover:border-gray-300 transition-shadow shadow-sm"
              >
                <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
                  {/* Job Details Header */}
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2 mb-2">
                      {/* Status Tag */}
                      <span
                        className={`inline-flex items-center gap-1 text-xs px-2.5 py-0.5 rounded-full font-medium ${style.bg} ${style.text}`}
                      >
                        <Icon className="w-3 h-3" />
                        {app.status.replace(/_/g, " ")}
                      </span>

                      {/* Match Score Badge */}
                      {app.match_score != null && (
                        <span
                          className={`inline-flex items-center gap-1 text-xs px-2.5 py-0.5 rounded-full font-semibold border ${getScoreBadgeColor(
                            score,
                          )}`}
                        >
                          <SparklesIcon className="w-3 h-3" />
                          {score.toFixed(1)}% Match
                        </span>
                      )}

                      {/* Auto-Apply Indicator for 85%+ */}
                      {isAutoApply && (
                        <span className="inline-flex items-center gap-1 text-xs px-2.5 py-0.5 rounded-full font-medium bg-purple-50 text-purple-700 border border-purple-200">
                          <ZapIcon className="w-3 h-3 text-purple-600 fill-purple-600" />
                          Auto-Apply (85%+ Match)
                        </span>
                      )}

                      {/* Portal Badge */}
                      <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded capitalize">
                        {portal}
                      </span>
                    </div>

                    {/* Job Title & Company */}
                    <div className="mt-1">
                      <h3 className="text-base font-bold text-gray-900 flex items-center gap-2 flex-wrap">
                        {jobTitle}
                        <span className="text-gray-400 font-normal">at</span>
                        <span className="text-blue-600 font-semibold">{companyName}</span>
                      </h3>

                      <div className="flex flex-wrap items-center gap-3 mt-1 text-xs text-gray-500">
                        {location && <span>📍 {location}</span>}
                        {app.job?.salary && <span>💰 {app.job.salary}</span>}
                        <span>
                          📅 Added {new Date(app.created_at).toLocaleDateString()}
                        </span>
                        {app.applied_at && (
                          <span className="text-green-600 font-medium">
                            ✓ Applied {new Date(app.applied_at).toLocaleDateString()}
                          </span>
                        )}
                        <span className="text-gray-400 font-mono text-[11px]">
                          Ref: {app.id.slice(0, 8)}...
                        </span>
                      </div>

                      {jobUrl && (
                        <a
                          href={jobUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 hover:underline mt-1.5 font-medium"
                        >
                          View Original Posting
                          <ExternalLinkIcon className="w-3 h-3" />
                        </a>
                      )}
                    </div>

                    {/* Confirmation number or error message */}
                    {app.confirmation_number && (
                      <div className="mt-2 text-xs bg-green-50 text-green-700 border border-green-200 rounded px-2.5 py-1 inline-block font-mono">
                        Confirmation: {app.confirmation_number}
                      </div>
                    )}
                    {app.error_message && (
                      <p className="text-xs text-red-600 mt-2 bg-red-50 p-2 rounded border border-red-200">
                        {app.error_message}
                      </p>
                    )}
                  </div>

                  {/* Actions Buttons */}
                  <div className="flex flex-wrap items-center gap-2 lg:flex-col lg:items-end shrink-0">
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
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                        resumeState === "ready"
                          ? "bg-white border-gray-200 text-gray-700 hover:bg-gray-50 cursor-pointer shadow-sm"
                          : "bg-gray-50 border-gray-200 text-gray-400 cursor-not-allowed"
                      }`}
                    >
                      <DownloadIcon className="w-3.5 h-3.5" />
                      {resumeState === "ready"
                        ? "Download Resume (PDF)"
                        : resumeState === "failed"
                        ? "Resume Failed"
                        : "Resume Generating..."}
                    </button>

                    {app.status !== "submitted" && app.status !== "rejected" && (
                      <button
                        onClick={() =>
                          setInterveneId(interveneId === app.id ? null : app.id)
                        }
                        className="flex items-center gap-1.5 bg-white border border-gray-200 text-gray-700 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-gray-50 transition-colors shadow-sm"
                      >
                        <UserCogIcon className="w-3.5 h-3.5 text-blue-600" />
                        {interveneId === app.id ? "Close" : "Manual Intervention"}
                      </button>
                    )}
                  </div>
                </div>

                {/* Manual Intervention Accordion */}
                {(interveneId === app.id ||
                  app.status === "needs_manual_review") && (
                  <div className="mt-4 p-4 bg-amber-50 border border-amber-200 rounded-lg text-sm">
                    <p className="font-semibold text-amber-900 mb-1 flex items-center gap-1.5">
                      <AlertCircleIcon className="w-4 h-4 text-amber-700" />
                      {app.status === "needs_manual_review"
                        ? "Auto-apply requires manual review (Login / CAPTCHA required)"
                        : "Manual Review & Action"}
                    </p>
                    <p className="text-xs text-amber-800 mb-3 leading-relaxed">
                      {app.error_message ||
                        "You can submit this application manually using the tailored PDF resume below."}
                    </p>

                    <div className="flex flex-wrap items-center gap-2">
                      {jobUrl && (
                        <a
                          href={jobUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 bg-blue-600 text-white px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-blue-700"
                        >
                          Open Job Posting <ExternalLinkIcon className="w-3 h-3" />
                        </a>
                      )}
                      {resumeState === "ready" && (
                        <button
                          onClick={() => handleDownloadResume(app.id)}
                          className="inline-flex items-center gap-1.5 bg-white border border-amber-300 text-amber-900 px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-amber-100"
                        >
                          <DownloadIcon className="w-3.5 h-3.5" /> Download Tailored PDF
                        </button>
                      )}
                      <button
                        onClick={() => markManualMutation.mutate(app.id)}
                        disabled={markManualMutation.isPending}
                        className="inline-flex items-center gap-1.5 bg-amber-600 text-white px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-amber-700 disabled:opacity-50"
                      >
                        <CheckCircleIcon className="w-3.5 h-3.5" />
                        Mark as Applied Manually
                      </button>
                    </div>
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
