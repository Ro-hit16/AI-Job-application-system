import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { applicationsApi, extractErrorDetail } from "../api/client";
import { useAuthStore } from "../store/auth";
import {
  CheckIcon,
  XIcon,
  EditIcon,
  DownloadIcon,
  FilterIcon,
  SparklesIcon,
  ExternalLinkIcon,
} from "lucide-react";

const MATCH_SCORE_RANGES = [
  { label: "All Match Scores", value: "all" },
  { label: "95%+ Match", value: "95+" },
  { label: "90% - 95%", value: "90-95" },
  { label: "85% - 90%", value: "85-90" },
  { label: "70% - 85%", value: "70-85" },
  { label: "50% - 70%", value: "50-70" },
];

export default function ApprovalQueue() {
  const queryClient = useQueryClient();
  const [editId, setEditId] = useState<string | null>(null);
  const [editNote, setEditNote] = useState("");
  const [matchFilter, setMatchFilter] = useState("all");
  const { user } = useAuthStore();

  const { data, isLoading } = useQuery({
    queryKey: ["pending"],
    queryFn: () => applicationsApi.pending(),
    refetchInterval: 30000,
  });

  const approveMutation = useMutation({
    mutationFn: ({ id, decision, note }: { id: string; decision: string; note?: string }) =>
      applicationsApi.approve(id, decision, note),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["pending"] }),
  });

  const rawApps = data?.data ?? [];

  // Filter pending applications by match score
  const filteredApps = useMemo(() => {
    return rawApps.filter((app: any) => {
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
        const targetApp = rawApps.find((app: any) => app.id === id);
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
      alert(await extractErrorDetail(err, "Could not download the updated resume."));
    }
  };

  const getScoreBadgeColor = (score: number) => {
    if (score >= 90) return "bg-emerald-50 text-emerald-700 border-emerald-200";
    if (score >= 85) return "bg-blue-50 text-blue-700 border-blue-200";
    if (score >= 70) return "bg-indigo-50 text-indigo-700 border-indigo-200";
    return "bg-amber-50 text-amber-700 border-amber-200";
  };

  if (isLoading) return <div className="p-6 text-gray-500">Loading approvals...</div>;

  return (
    <div className="p-4 sm:p-6 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Approval Queue</h1>
          <p className="text-sm text-gray-500 mt-1">
            {filteredApps.length} of {rawApps.length} application(s) ready for your review
          </p>
        </div>

        {/* Match Score Filter */}
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

      {filteredApps.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-400 shadow-sm">
          {rawApps.length === 0
            ? "No pending approvals — run the agent pipeline in Settings to find new matching jobs."
            : "No applications in the approval queue match your selected match score filter."}
        </div>
      ) : (
        <div className="space-y-4">
          {filteredApps.map((app: any) => {
            const score = app.match_score ?? 0;
            return (
              <div key={app.id} className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm hover:border-gray-300 transition-colors">
                {/* Job Info Header */}
                <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-2 mb-3">
                  <div>
                    <h3 className="font-bold text-gray-900 text-lg">
                      {app.job?.title ?? "Software Engineer"} at{" "}
                      <span className="text-blue-600">{app.job?.company ?? "Tech Company"}</span>
                    </h3>
                    <div className="flex flex-wrap items-center gap-3 mt-1.5 text-xs text-gray-500">
                      {app.job?.location && <span>📍 {app.job.location}</span>}
                      {app.job?.salary && <span>💰 {app.job.salary}</span>}
                      {app.job?.portal && (
                        <span>
                          🔗 via <span className="capitalize font-semibold text-gray-700">{app.job.portal}</span>
                        </span>
                      )}
                      {app.match_score != null && (
                        <span
                          className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-semibold border ${getScoreBadgeColor(
                            score,
                          )}`}
                        >
                          <SparklesIcon className="w-3 h-3" />
                          {score.toFixed(1)}% Match
                        </span>
                      )}
                      <span>📅 {new Date(app.created_at).toLocaleDateString()}</span>
                    </div>

                    {app.job?.url && (
                      <a
                        href={app.job.url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline mt-2 font-medium"
                      >
                        View Original Job Posting
                        <ExternalLinkIcon className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                  <span className="bg-amber-100 text-amber-800 text-xs px-2.5 py-1 rounded-full font-medium shrink-0">
                    Pending Review
                  </span>
                </div>

                {/* Tailored Resume Download Section */}
                <div className="mb-4 p-3 bg-gray-50 rounded-lg flex items-center justify-between gap-3 border border-gray-100">
                  <div className="min-w-0">
                    <p className="text-xs text-gray-500 mb-0.5 font-medium">Tailored Resume</p>
                    <p className="text-xs text-gray-700 truncate">
                      {app.tailored_resume_path
                        ? "Ready to review & download"
                        : app.error_message?.startsWith("Resume tailoring failed")
                        ? "Generation failed — will regenerate on approval"
                        : "Ready for automatic generation on approval"}
                    </p>
                  </div>
                  <button
                    onClick={() => handleDownloadResume(app.id)}
                    disabled={!app.tailored_resume_path}
                    title={
                      app.tailored_resume_path
                        ? "Download tailored PDF resume"
                        : "Resume will be generated when approved"
                    }
                    className={`flex items-center gap-1.5 shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                      app.tailored_resume_path
                        ? "bg-white border-gray-200 text-gray-700 hover:bg-gray-100 cursor-pointer shadow-sm"
                        : "bg-gray-50 border-gray-200 text-gray-400 cursor-not-allowed"
                    }`}
                  >
                    <DownloadIcon className="w-3.5 h-3.5" />
                    {app.tailored_resume_path ? "Download Tailored PDF" : "Resume Not Ready"}
                  </button>
                </div>

                {/* Edit Instructions Box */}
                {editId === app.id && (
                  <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                    <p className="text-xs font-semibold text-blue-900 mb-1">
                      Edit Instructions — customize tailoring prior to application submission:
                    </p>
                    <textarea
                      className="w-full border border-blue-200 rounded-lg p-2.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                      placeholder="e.g. Highlight my React and Node.js microservices experience..."
                      rows={3}
                      value={editNote}
                      onChange={(e) => setEditNote(e.target.value)}
                    />
                  </div>
                )}

                {/* Action Buttons */}
                <div className="flex flex-wrap gap-2 pt-2 border-t border-gray-100">
                  <button
                    onClick={() =>
                      approveMutation.mutate({ id: app.id, decision: "approve", note: editNote })
                    }
                    disabled={approveMutation.isPending}
                    className="flex items-center gap-1.5 bg-green-600 text-white px-4 py-2 rounded-lg text-xs font-medium hover:bg-green-700 disabled:opacity-50 shadow-sm"
                  >
                    <CheckIcon className="w-3.5 h-3.5" /> Approve & Apply
                  </button>
                  <button
                    onClick={() => approveMutation.mutate({ id: app.id, decision: "reject" })}
                    disabled={approveMutation.isPending}
                    className="flex items-center gap-1.5 bg-red-50 text-red-700 border border-red-200 px-4 py-2 rounded-lg text-xs font-medium hover:bg-red-100 disabled:opacity-50"
                  >
                    <XIcon className="w-3.5 h-3.5" /> Reject
                  </button>
                  <button
                    onClick={() => {
                      setEditId(editId === app.id ? null : app.id);
                      setEditNote("");
                    }}
                    className="flex items-center gap-1.5 bg-gray-50 text-gray-700 border border-gray-200 px-4 py-2 rounded-lg text-xs font-medium hover:bg-gray-100"
                  >
                    <EditIcon className="w-3.5 h-3.5" />{" "}
                    {editId === app.id ? "Cancel Note" : "Custom Instructions"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
