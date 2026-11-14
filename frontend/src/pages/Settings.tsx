// src/pages/Settings.tsx
import { useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { agentsApi, resumesApi, extractErrorDetail } from "../api/client";
import {
  UploadIcon,
  PlayIcon,
  TrashIcon,
  Code2Icon,
  CheckCircle2Icon,
  RotateCcwIcon,
  CopyIcon,
  FileCode2Icon,
  SparklesIcon,
} from "lucide-react";

export default function Settings() {
  const isRunning = useRef(false);
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [runStatus, setRunStatus] = useState<string>("");
  const [uploadError, setUploadError] = useState<string>("");

  // LaTeX Template state
  const [templateTex, setTemplateTex] = useState<string>("");
  const [isTemplateLoaded, setIsTemplateLoaded] = useState(false);
  const [templateMsg, setTemplateMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [isSavingTemplate, setIsSavingTemplate] = useState(false);
  const [isResettingTemplate, setIsResettingTemplate] = useState(false);
  const [copiedTemplate, setCopiedTemplate] = useState(false);
  const texFileRef = useRef<HTMLInputElement>(null);

  const { data: templateData, refetch: refetchTemplate } = useQuery({
    queryKey: ["resume-template"],
    queryFn: async () => {
      const res = await resumesApi.getTemplate();
      if (!isTemplateLoaded && res.data.template) {
        setTemplateTex(res.data.template);
        setIsTemplateLoaded(true);
      }
      return res.data;
    },
  });

  const isCustomTemplate = templateData?.is_custom ?? false;

  const handleSaveTemplate = async () => {
    if (!templateTex.trim()) {
      setTemplateMsg({ type: "error", text: "Template cannot be empty." });
      return;
    }
    setIsSavingTemplate(true);
    setTemplateMsg(null);
    try {
      const res = await resumesApi.saveTemplate(templateTex);
      setTemplateMsg({ type: "success", text: res.data.message || "Template saved successfully! Tailored resumes will now use your custom template." });
      refetchTemplate();
    } catch (err: any) {
      const detail = err.response?.data?.detail || err.message || "Failed to save template.";
      setTemplateMsg({ type: "error", text: detail });
    } finally {
      setIsSavingTemplate(false);
    }
  };

  const handleResetTemplate = async () => {
    if (!window.confirm("Are you sure you want to reset your resume template back to the system default Overleaf template?")) {
      return;
    }
    setIsResettingTemplate(true);
    setTemplateMsg(null);
    try {
      const res = await resumesApi.resetTemplate();
      setTemplateTex(res.data.template);
      setTemplateMsg({ type: "success", text: "Template reset to system default!" });
      refetchTemplate();
    } catch (err: any) {
      const detail = err.response?.data?.detail || err.message || "Failed to reset template.";
      setTemplateMsg({ type: "error", text: detail });
    } finally {
      setIsResettingTemplate(false);
    }
  };

  const handleCopyTemplate = () => {
    navigator.clipboard.writeText(templateTex);
    setCopiedTemplate(true);
    setTimeout(() => setCopiedTemplate(false), 2000);
  };

  const handleUploadTexFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const content = ev.target?.result as string;
      if (content) {
        setTemplateTex(content);
        setTemplateMsg({ type: "success", text: `Loaded content from ${file.name}. Click 'Save Template' to apply.` });
      }
    };
    reader.readAsText(file);
    e.target.value = "";
  };

  const { data: resumesData } = useQuery({
    queryKey: ["resumes"],
    queryFn: () => resumesApi.list(),
  });
  const resumes = resumesData?.data ?? [];

  const uploadMutation = useMutation({
    mutationFn: (file: File) => resumesApi.upload(file),
    onSuccess: () => {
      setUploadError("");
      queryClient.invalidateQueries({ queryKey: ["resumes"] });
    },
    onError: async (err) => {
      setUploadError(await extractErrorDetail(err, "Upload failed. Please try again."));
    },
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
    <div className="p-4 sm:p-6 max-w-2xl mx-auto">
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
          onChange={(e) => {
            if (e.target.files?.[0]) {
              setUploadError("");
              uploadMutation.mutate(e.target.files[0]);
            }
            e.target.value = "";
          }}
        />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploadMutation.isPending}
          className="flex items-center gap-2 border border-dashed border-gray-300 rounded-lg px-4 py-3 text-sm text-gray-600 hover:border-blue-400 hover:text-blue-600 w-full justify-center"
        >
          <UploadIcon className="w-4 h-4" />
          {uploadMutation.isPending ? "Uploading..." : "Upload PDF Resume"}
        </button>
        {uploadError && (
          <p className="text-xs text-red-500 mt-2">{uploadError}</p>
        )}
      </div>

      {/* Resume LaTeX (.tex) Template Management */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 mb-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Code2Icon className="w-5 h-5 text-indigo-600" />
            <h2 className="font-semibold text-gray-800">Resume LaTeX Template (.tex)</h2>
          </div>
          <span
            className={`text-xs px-2.5 py-1 rounded-full font-medium ${
              isCustomTemplate
                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                : "bg-gray-100 text-gray-600 border border-gray-200"
            }`}
          >
            {isCustomTemplate ? "✅ Custom Template Active" : "Default Template Active"}
          </span>
        </div>

        <p className="text-xs text-gray-500 mb-3 leading-relaxed">
          Paste your own LaTeX (<span className="font-mono text-gray-700">.tex</span>) template from Overleaf. The tailoring agent and Instant Tailor will dynamically use your structure, sections, styling, and fonts.
        </p>

        {templateMsg && (
          <div
            className={`p-3 rounded-lg text-xs mb-3 flex items-start gap-2 ${
              templateMsg.type === "success"
                ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                : "bg-red-50 text-red-800 border border-red-200"
            }`}
          >
            {templateMsg.type === "success" ? (
              <CheckCircle2Icon className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
            ) : null}
            <span>{templateMsg.text}</span>
          </div>
        )}

        <div className="relative mb-3">
          <textarea
            value={templateTex}
            onChange={(e) => setTemplateTex(e.target.value)}
            rows={14}
            className="w-full font-mono text-xs p-3.5 bg-gray-900 text-emerald-300 rounded-lg border border-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 leading-relaxed resize-y"
            placeholder="Paste your \documentclass[...]{article} ... \end{document} template here..."
            spellCheck={false}
          />
          <div className="flex justify-between items-center text-[11px] text-gray-400 mt-1 px-1">
            <span>{templateTex.length.toLocaleString()} characters · {templateTex.split("\n").length} lines</span>
            <span>Must contain \documentclass and egin&#123;document&#125;</span>
          </div>
        </div>

        <input
          ref={texFileRef}
          type="file"
          accept=".tex,.txt"
          className="hidden"
          onChange={handleUploadTexFile}
        />

        <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-gray-100">
          <div className="flex items-center gap-2">
            <button
              onClick={() => texFileRef.current?.click()}
              type="button"
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors"
            >
              <FileCode2Icon className="w-3.5 h-3.5" />
              Upload .tex File
            </button>
            <button
              onClick={handleCopyTemplate}
              type="button"
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors"
            >
              <CopyIcon className="w-3.5 h-3.5" />
              {copiedTemplate ? "Copied!" : "Copy Code"}
            </button>
            {isCustomTemplate && (
              <button
                onClick={handleResetTemplate}
                disabled={isResettingTemplate}
                type="button"
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-rose-700 bg-rose-50 hover:bg-rose-100 rounded-md transition-colors disabled:opacity-50"
              >
                <RotateCcwIcon className="w-3.5 h-3.5" />
                {isResettingTemplate ? "Resetting..." : "Reset to Default"}
              </button>
            )}
          </div>

          <button
            onClick={handleSaveTemplate}
            disabled={isSavingTemplate}
            type="button"
            className="flex items-center gap-1.5 bg-indigo-600 text-white px-4 py-1.5 rounded-md text-xs font-medium hover:bg-indigo-700 transition-colors disabled:opacity-50 shadow-sm"
          >
            <SparklesIcon className="w-3.5 h-3.5" />
            {isSavingTemplate ? "Validating & Saving..." : "Save Template"}
          </button>
        </div>
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