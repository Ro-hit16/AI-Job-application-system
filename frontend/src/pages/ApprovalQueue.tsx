import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { applicationsApi, extractErrorDetail } from "../api/client";
import { CheckIcon, XIcon, EditIcon, DownloadIcon } from "lucide-react";

export default function ApprovalQueue() {
  const queryClient = useQueryClient();
  const [editId, setEditId] = useState<string | null>(null);
  const [editNote, setEditNote] = useState("");

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

  const apps = data?.data ?? [];

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
      alert(await extractErrorDetail(err, "Could not download the updated resume."));
    }
  };

  if (isLoading) return <div className="p-6 text-gray-500">Loading approvals...</div>;

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Approval Queue</h1>
      <p className="text-sm text-gray-500 mb-6">{apps.length} application(s) waiting for your review</p>

      {apps.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-400">
          No pending approvals — run the agent pipeline to find new jobs.
        </div>
      ) : (
        <div className="space-y-4">
          {apps.map((app: any) => (
            <div key={app.id} className="bg-white rounded-xl border border-gray-200 p-6">
              
              {/* Job Info Header */}
              <div className="flex justify-between items-start mb-3">
                <div>
                  <h3 className="font-semibold text-gray-900 text-lg">
                    {app.job?.title ?? "Unknown Position"} at {app.job?.company ?? "Unknown Company"}
                  </h3>
                  <div className="flex flex-wrap gap-3 mt-1 text-sm text-gray-500">
                    {app.job?.location && <span>📍 {app.job.location}</span>}
                    {app.job?.salary && <span>💰 {app.job.salary}</span>}
                    {app.job?.portal && (
                      <span>🔗 via <span className="capitalize font-medium">{app.job.portal}</span></span>
                    )}
                    <span>🎯 Match: <span className="font-semibold text-blue-600">{app.match_score?.toFixed(1)}%</span></span>
                    <span>📅 {new Date(app.created_at).toLocaleDateString()}</span>
                  </div>
                  {app.job?.url && (
                    <a href={app.job.url} target="_blank" rel="noreferrer"
                      className="text-xs text-blue-500 hover:underline mt-1 inline-block">
                      View original job posting ↗
                    </a>
                  )}
                </div>
                <span className="bg-amber-100 text-amber-700 text-xs px-2 py-1 rounded-full shrink-0">Pending</span>
              </div>

              {/* Tailored Resume */}
              {app.tailored_resume_path && (
                <div className="mb-4 p-3 bg-gray-50 rounded-lg flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs text-gray-500 mb-1">Tailored Resume</p>
                    <p className="text-sm text-gray-700 font-mono truncate">{app.tailored_resume_path}</p>
                  </div>
                  <button
                    onClick={() => handleDownloadResume(app.id)}
                    className="flex items-center gap-1.5 shrink-0 bg-white border border-gray-200 text-gray-700 px-3 py-1.5 rounded-lg text-sm hover:bg-gray-100"
                  >
                    <DownloadIcon className="w-4 h-4" /> Download Updated Resume
                  </button>
                </div>
              )}

              {/* Edit Instructions Box */}
              {editId === app.id && (
                <div className="mb-3">
                  <p className="text-xs text-gray-500 mb-1">
                    Edit Instructions — tell the AI how to modify the application before submitting
                  </p>
                  <textarea
                    className="w-full border border-gray-200 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="e.g. Emphasize my FastAPI experience, remove the internship from 2019..."
                    rows={3}
                    value={editNote}
                    onChange={(e) => setEditNote(e.target.value)}
                  />
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex gap-2">
                <button
                  onClick={() => approveMutation.mutate({ id: app.id, decision: "approve", note: editNote })}
                  disabled={approveMutation.isPending}
                  className="flex items-center gap-1.5 bg-green-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-green-700 disabled:opacity-50"
                >
                  <CheckIcon className="w-4 h-4" /> Approve & Apply
                </button>
                <button
                  onClick={() => approveMutation.mutate({ id: app.id, decision: "reject" })}
                  disabled={approveMutation.isPending}
                  className="flex items-center gap-1.5 bg-red-100 text-red-700 px-4 py-2 rounded-lg text-sm hover:bg-red-200 disabled:opacity-50"
                >
                  <XIcon className="w-4 h-4" /> Reject
                </button>
                <button
                  onClick={() => { setEditId(editId === app.id ? null : app.id); setEditNote(""); }}
                  className="flex items-center gap-1.5 bg-gray-100 text-gray-700 px-4 py-2 rounded-lg text-sm hover:bg-gray-200"
                >
                  <EditIcon className="w-4 h-4" /> {editId === app.id ? "Cancel Edit" : "Edit Instructions"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}