// src/pages/Settings.tsx
import { useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { agentsApi, resumesApi } from "../api/client";
import { UploadIcon, PlayIcon, TrashIcon } from "lucide-react";

export default function Settings() {
  const isRunning = useRef(false);
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [runStatus, setRunStatus] = useState<string>("");

  const { data: resumesData } = useQuery({
    queryKey: ["resumes"],
    queryFn: () => resumesApi.list(),
  });
  const resumes = resumesData?.data ?? [];

  const uploadMutation = useMutation({
    mutationFn: (file: File) => resumesApi.upload(file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["resumes"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => resumesApi.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["resumes"] }),
  });

  const runMutation = useMutation({
    mutationFn: (resumeId: string) => agentsApi.run({ resume_id: resumeId }),
    onSuccess: () => setRunStatus("Pipeline started! Check the Approval Queue for results."),
    onError: () => setRunStatus("Failed to start pipeline."),
  });

  const primaryResume = resumes.find((r: any) => r.is_primary) ?? resumes[0];

  const handleRunPipeline = () => {
    if (isRunning.current || !primaryResume) return;
    isRunning.current = true;
    runMutation.mutate(primaryResume.id, {
      onSettled: () => { isRunning.current = false; }
    });
  };

  return (
    <div className="p-6 max-w-2xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Settings</h1>

      {/* Resume Upload */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 mb-4">
        <h2 className="font-semibold text-gray-800 mb-4">Resumes</h2>
        <div className="space-y-3 mb-4">
          {resumes.map((r: any) => (
            <div key={r.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
              <div>
                <p className="text-sm font-medium text-gray-800">{r.original_filename}</p>
                <p className="text-xs text-gray-500">
                  {r.is_primary ? "✅ Primary" : "Secondary"} · {r.is_parsed ? "Parsed" : "Not parsed"}
                </p>
              </div>
              <button
                onClick={() => deleteMutation.mutate(r.id)}
                className="text-red-400 hover:text-red-600"
              >
                <TrashIcon className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && uploadMutation.mutate(e.target.files[0])}
        />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploadMutation.isPending}
          className="flex items-center gap-2 border border-dashed border-gray-300 rounded-lg px-4 py-3 text-sm text-gray-600 hover:border-blue-400 hover:text-blue-600 w-full justify-center"
        >
          <UploadIcon className="w-4 h-4" />
          {uploadMutation.isPending ? "Uploading..." : "Upload PDF Resume"}
        </button>
      </div>

      {/* Run Pipeline */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="font-semibold text-gray-800 mb-2">Run Agent Pipeline</h2>
        <p className="text-sm text-gray-500 mb-4">
          Searches job portals, matches against your resume, tailors applications, and queues for approval.
        </p>
        {runStatus && <p className="text-sm text-green-600 mb-3">{runStatus}</p>}
        <button
          onClick={handleRunPipeline}
          disabled={runMutation.isPending || !primaryResume}
          className="flex items-center gap-2 bg-blue-600 text-white px-5 py-2.5 rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50"
        >
          <PlayIcon className="w-4 h-4" />
          {runMutation.isPending ? "Starting..." : "Run Now"}
        </button>
        {!primaryResume && <p className="text-xs text-red-500 mt-2">Upload a resume first</p>}
      </div>
    </div>
  );
}