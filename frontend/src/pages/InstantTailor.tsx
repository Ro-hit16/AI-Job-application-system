import { useState } from "react";
import {
  SparklesIcon,
  DownloadIcon,
  CheckCircle2Icon,
  CopyIcon,
  ExternalLinkIcon,
  Wand2Icon,
  RefreshCwIcon,
  FileTextIcon,
  Code2Icon,
  ArrowRightIcon,
  LayersIcon,
} from "lucide-react";
import { resumesApi } from "../api/client";
import { ChevronDownIcon, ChevronUpIcon, RotateCcwIcon } from "lucide-react";

const SAMPLE_JD = `Role: Senior Full-Stack Developer
Company: TechFlow Innovations
Location: Remote / Hybrid

About the Role:
We are seeking a talented Senior Full-Stack Developer proficient in React.js, Node.js, and TypeScript. You will be responsible for designing and deploying high-performance microservices, creating responsive web applications, and designing robust RESTful APIs with MongoDB and PostgreSQL.

Requirements & Skills:
- 3+ years of experience with React.js, TypeScript, and modern frontend state management.
- Strong proficiency in Node.js and Express.js for backend microservices architecture.
- Hands-on experience with MongoDB, PostgreSQL, and database schema optimization.
- Familiarity with Docker, CI/CD pipelines, and cloud services (AWS EC2, S3).
- Experience integrating AI-powered capabilities or LLM workflows is a huge plus.
- Collaborative mindset, following Agile/Scrum best practices and writing clean, tested code.`;

interface BulletChange {
  original: string;
  tailored: string;
  reason?: string;
}

interface TailorResponse {
  tailor_id: string;
  matched_skills: string[];
  highlighted_skills: string[];
  match_score: number;
  bullet_changes: BulletChange[];
  download_url: string;
  filename: string;
}

export default function InstantTailor() {
  const [jobTitle, setJobTitle] = useState("Full-Stack Developer");
  const [company, setCompany] = useState("");
  const [instructions, setInstructions] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [result, setResult] = useState<TailorResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Dynamic LaTeX template state
  const [showTemplateEditor, setShowTemplateEditor] = useState(false);
  const [customTemplate, setCustomTemplate] = useState<string>("");
  const [templateLoaded, setTemplateLoaded] = useState(false);
  const [savingDefaultStatus, setSavingDefaultStatus] = useState<string>("");

  const handleToggleTemplate = async () => {
    const nextState = !showTemplateEditor;
    setShowTemplateEditor(nextState);
    if (nextState && !templateLoaded) {
      try {
        const res = await resumesApi.getTemplate();
        setCustomTemplate(res.data.template);
        setTemplateLoaded(true);
      } catch (err) {
        console.error("Could not fetch active template:", err);
      }
    }
  };

  const handleSaveAsDefault = async () => {
    if (!customTemplate.trim()) return;
    setSavingDefaultStatus("Saving...");
    try {
      await resumesApi.saveTemplate(customTemplate);
      setSavingDefaultStatus("Saved as default template!");
      setTimeout(() => setSavingDefaultStatus(""), 3000);
    } catch (err: any) {
      setSavingDefaultStatus(err.response?.data?.detail || "Failed to save.");
      setTimeout(() => setSavingDefaultStatus(""), 3000);
    }
  };

  const handleResetToSystemDefault = async () => {
    try {
      const res = await resumesApi.getTemplate();
      setCustomTemplate(res.data.default_template || res.data.template);
    } catch (err) {
      console.error(err);
    }
  };

  const handleUseSample = () => {
    setJobTitle("Senior Full-Stack Developer");
    setCompany("TechFlow Innovations");
    setInstructions("Emphasize React, Node.js microservices, Docker, and AI/LLM integration");
    setJobDescription(SAMPLE_JD);
  };

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!jobDescription.trim() || jobDescription.trim().length < 20) {
      setError("Please paste a job description (at least 20 characters).");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await resumesApi.tailorInstant({
        job_title: jobTitle,
        company,
        job_description: jobDescription,
        instructions,
        custom_template: showTemplateEditor && customTemplate.trim() ? customTemplate.trim() : undefined,
      });
      setResult(res.data);
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || "Failed to tailor resume.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadPdf = async () => {
    if (!result) return;
    setDownloading(true);
    try {
      const res = await resumesApi.downloadInstant(result.tailor_id, result.filename);
      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = result.filename.endsWith(".pdf") ? result.filename : `${result.filename}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      alert("Failed to download PDF: " + (err.message || "Unknown error"));
    } finally {
      setDownloading(false);
    }
  };

  const handleOpenPdf = async () => {
    if (!result) return;
    setDownloading(true);
    try {
      const res = await resumesApi.downloadInstant(result.tailor_id, result.filename);
      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      window.open(url, "_blank");
    } catch (err: any) {
      alert("Failed to open PDF: " + (err.message || "Unknown error"));
    } finally {
      setDownloading(false);
    }
  };

  const handleCopySummary = () => {
    if (!result) return;
    const text = [
      `Target Role: ${jobTitle} ${company ? `at ${company}` : ""}`,
      `Match Score: ${result.match_score}%`,
      `Matched Skills: ${result.matched_skills.join(", ")}`,
      "",
      "Key Modifications:",
      ...result.bullet_changes.map(
        (b, i) => `${i + 1}. ${b.reason || "Adapted bullet"}\n   → ${b.tailored}`
      ),
    ].join("\n");

    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Top Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-gradient-to-r from-blue-700 via-indigo-700 to-purple-800 text-white rounded-2xl p-6 shadow-lg shadow-blue-500/10">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="p-1.5 bg-white/20 rounded-lg">
              <Wand2Icon className="w-5 h-5 text-blue-200" />
            </span>
            <span className="text-xs font-semibold uppercase tracking-wider text-blue-200">
              Instant AI Resume Tailor
            </span>
          </div>
          <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight">
            Direct JD Resume Matcher & PDF Generator
          </h1>
          <p className="text-blue-100 text-sm mt-1 max-w-2xl">
            Paste any Job Description (JD) below. The AI extracts target competencies, aligns your
            experience and summary, and instantly generates a production-ready single-page PDF.
          </p>
        </div>

        <button
          onClick={handleUseSample}
          type="button"
          className="self-start md:self-center px-4 py-2 bg-white/10 hover:bg-white/20 text-white text-xs font-medium rounded-xl border border-white/20 transition-all flex items-center gap-2 shrink-0 shadow-sm"
        >
          <SparklesIcon className="w-4 h-4 text-amber-300" />
          Load Sample Full-Stack JD
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-xs font-bold text-red-600 hover:text-red-800">
            Dismiss
          </button>
        </div>
      )}

      {/* Main Grid: Input Form (Left) & Live Results (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Form (5 Cols) */}
        <div className="lg:col-span-5 bg-white rounded-2xl border border-gray-200 p-6 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-gray-100 pb-3">
            <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
              <FileTextIcon className="w-4 h-4 text-blue-600" />
              Job Details & Description
            </h2>
            <span className="text-xs text-gray-400">Step 1 of 2</span>
          </div>

          <form onSubmit={handleGenerate} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Job Title <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Full-Stack Engineer"
                  value={jobTitle}
                  onChange={(e) => setJobTitle(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-gray-50/50"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Company Name <span className="text-gray-400 font-normal">(optional)</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. Google, Stripe"
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-gray-50/50"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">
                Custom Focus / Instructions <span className="text-gray-400 font-normal">(optional)</span>
              </label>
              <input
                type="text"
                placeholder="e.g. Emphasize backend APIs, Docker, and MongoDB query optimization"
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-gray-50/50"
              />
            </div>

            <div>
              <div className="flex justify-between items-center mb-1">
                <label className="block text-xs font-semibold text-gray-700">
                  Paste Job Description (JD) <span className="text-red-500">*</span>
                </label>
                <span className="text-[11px] text-gray-400">
                  {jobDescription.length} characters
                </span>
              </div>
              <textarea
                required
                rows={10}
                placeholder="Paste the full job requirements, skills, and responsibilities here..."
                value={jobDescription}
                onChange={(e) => setJobDescription(e.target.value)}
                className="w-full p-3 border border-gray-200 rounded-xl text-xs font-mono leading-relaxed focus:outline-none focus:ring-2 focus:ring-blue-500 bg-gray-50/30 resize-y"
              />
            </div>

            {/* Dynamic LaTeX Template Accordion */}
            <div className="border border-gray-200 rounded-xl overflow-hidden bg-gray-50/40">
              <button
                type="button"
                onClick={handleToggleTemplate}
                className="w-full px-3.5 py-2.5 flex items-center justify-between text-left hover:bg-gray-100/60 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <Code2Icon className="w-4 h-4 text-indigo-600" />
                  <span className="text-xs font-semibold text-gray-800">
                    Customize Resume .tex Template
                  </span>
                  {showTemplateEditor && customTemplate.trim() && (
                    <span className="text-[10px] bg-indigo-50 text-indigo-700 font-medium px-2 py-0.5 rounded-full border border-indigo-200">
                      Custom .tex Active
                    </span>
                  )}
                </div>
                {showTemplateEditor ? (
                  <ChevronUpIcon className="w-4 h-4 text-gray-400" />
                ) : (
                  <ChevronDownIcon className="w-4 h-4 text-gray-400" />
                )}
              </button>

              {showTemplateEditor && (
                <div className="p-3 border-t border-gray-200 bg-white space-y-2">
                  <div className="flex items-center justify-between text-[11px] text-gray-500">
                    <span>Paste or edit your LaTeX (.tex) template below:</span>
                    <button
                      type="button"
                      onClick={handleResetToSystemDefault}
                      className="text-indigo-600 hover:text-indigo-800 flex items-center gap-1 font-medium"
                    >
                      <RotateCcwIcon className="w-3 h-3" />
                      Reset to Default
                    </button>
                  </div>
                  <textarea
                    rows={8}
                    value={customTemplate}
                    onChange={(e) => setCustomTemplate(e.target.value)}
                    placeholder="\documentclass{article} ... \end{document}"
                    className="w-full p-2.5 font-mono text-[11px] bg-gray-900 text-emerald-300 rounded-lg border border-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 leading-relaxed"
                    spellCheck={false}
                  />
                  <div className="flex items-center justify-between pt-1">
                    <span className="text-[10px] text-gray-400">
                      {customTemplate.length.toLocaleString()} chars · will be used for this tailoring session
                    </span>
                    <button
                      type="button"
                      onClick={handleSaveAsDefault}
                      className="text-xs px-3 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-medium rounded-lg border border-indigo-200 transition-colors"
                    >
                      {savingDefaultStatus || "Save as My Default Template"}
                    </button>
                  </div>
                </div>
              )}
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 px-4 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-semibold text-sm rounded-xl shadow-md shadow-blue-500/20 disabled:opacity-50 transition-all flex items-center justify-center gap-2 cursor-pointer"
            >
              {loading ? (
                <>
                  <RefreshCwIcon className="w-4 h-4 animate-spin text-white" />
                  Tailoring & Rendering PDF...
                </>
              ) : (
                <>
                  <SparklesIcon className="w-4 h-4 text-amber-300" />
                  Tailor Resume & Generate PDF
                </>
              )}
            </button>
          </form>
        </div>

        {/* Right Column: Results & PDF Downloads (7 Cols) */}
        <div className="lg:col-span-7 space-y-5">
          {!result && !loading && (
            <div className="bg-white rounded-2xl border border-gray-200 p-8 text-center space-y-6 shadow-sm">
              <div className="w-16 h-16 bg-blue-50 rounded-2xl flex items-center justify-center mx-auto text-blue-600">
                <LayersIcon className="w-8 h-8" />
              </div>
              <div className="max-w-md mx-auto space-y-2">
                <h3 className="text-lg font-bold text-gray-900">
                  Ready to tailor your resume
                </h3>
                <p className="text-xs text-gray-500 leading-relaxed">
                  Paste any job description on the left and click{" "}
                  <span className="font-semibold text-gray-700">"Tailor Resume & Generate PDF"</span>.
                  The system will analyze required skills, tailor your achievements, and render a single-page PDF formatted cleanly.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-left max-w-lg mx-auto pt-2">
                <div className="bg-gray-50 p-3.5 rounded-xl border border-gray-100">
                  <div className="w-6 h-6 bg-blue-100 rounded-lg text-blue-700 flex items-center justify-center text-xs font-bold mb-2">
                    1
                  </div>
                  <h4 className="text-xs font-semibold text-gray-800">Skill Extraction</h4>
                  <p className="text-[11px] text-gray-500 mt-1">
                    Detects frameworks, tools, and technical requirements from the JD.
                  </p>
                </div>

                <div className="bg-gray-50 p-3.5 rounded-xl border border-gray-100">
                  <div className="w-6 h-6 bg-indigo-100 rounded-lg text-indigo-700 flex items-center justify-center text-xs font-bold mb-2">
                    2
                  </div>
                  <h4 className="text-xs font-semibold text-gray-800">Bullet Tailoring</h4>
                  <p className="text-[11px] text-gray-500 mt-1">
                    Adapts experience bullets to prominently showcase matched capabilities.
                  </p>
                </div>

                <div className="bg-gray-50 p-3.5 rounded-xl border border-gray-100">
                  <div className="w-6 h-6 bg-green-100 rounded-lg text-green-700 flex items-center justify-center text-xs font-bold mb-2">
                    3
                  </div>
                  <h4 className="text-xs font-semibold text-gray-800">Instant PDF</h4>
                  <p className="text-[11px] text-gray-500 mt-1">
                    Directly downloads a styled single-page PDF with no LaTeX errors.
                  </p>
                </div>
              </div>
            </div>
          )}

          {loading && (
            <div className="bg-white rounded-2xl border border-gray-200 p-12 text-center shadow-sm space-y-4">
              <div className="relative w-16 h-16 mx-auto">
                <div className="w-16 h-16 rounded-full border-4 border-blue-100 border-t-blue-600 animate-spin" />
                <SparklesIcon className="w-6 h-6 text-blue-600 absolute inset-0 m-auto" />
              </div>
              <h3 className="text-base font-bold text-gray-900">
                Tailoring Resume to Job Description...
              </h3>
              <p className="text-xs text-gray-500 max-w-sm mx-auto">
                Extracting technical keywords, rewriting key experience points, and compiling your tailored single-page PDF.
              </p>
            </div>
          )}

          {result && !loading && (
            <div className="space-y-5 animate-in fade-in duration-300">
              {/* Summary Score Card */}
              <div className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-gray-100 pb-5">
                  <div className="flex items-center gap-4">
                    <div className="relative flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-tr from-blue-600 to-indigo-600 text-white font-extrabold text-xl shadow-md shadow-blue-500/20">
                      {result.match_score}%
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-green-100 text-green-700">
                          Tailoring Complete
                        </span>
                        <span className="text-xs text-gray-400">PDF Ready</span>
                      </div>
                      <h3 className="text-lg font-bold text-gray-900 mt-0.5">
                        {jobTitle} {company ? `at ${company}` : ""}
                      </h3>
                      <p className="text-xs text-gray-500">
                        {result.matched_skills.length} core candidate skills matched directly with the JD
                      </p>
                    </div>
                  </div>

                  {/* Top Actions */}
                  <div className="flex flex-wrap gap-2 shrink-0">
                    <button
                      onClick={handleDownloadPdf}
                      disabled={downloading}
                      className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-xl transition-colors flex items-center gap-2 shadow-sm cursor-pointer disabled:opacity-50"
                    >
                      <DownloadIcon className="w-4 h-4" />
                      {downloading ? "Downloading..." : "Download PDF"}
                    </button>

                    <button
                      onClick={handleOpenPdf}
                      disabled={downloading}
                      className="px-3 py-2.5 bg-gray-50 hover:bg-gray-100 text-gray-700 text-xs font-semibold rounded-xl border border-gray-200 transition-colors flex items-center gap-1.5 cursor-pointer"
                      title="Open PDF in new tab"
                    >
                      <ExternalLinkIcon className="w-4 h-4 text-gray-500" />
                      Preview
                    </button>

                    <button
                      onClick={handleCopySummary}
                      className="px-3 py-2.5 bg-gray-50 hover:bg-gray-100 text-gray-700 text-xs font-semibold rounded-xl border border-gray-200 transition-colors flex items-center gap-1.5 cursor-pointer"
                      title="Copy tailored overview"
                    >
                      {copied ? (
                        <CheckCircle2Icon className="w-4 h-4 text-green-600" />
                      ) : (
                        <CopyIcon className="w-4 h-4 text-gray-500" />
                      )}
                      {copied ? "Copied" : "Copy"}
                    </button>
                  </div>
                </div>

                {/* Skills Matched Chips */}
                <div className="pt-4 space-y-3">
                  <div>
                    <span className="text-xs font-semibold text-gray-700 block mb-2">
                      Key JD Competencies Highlighted in Resume:
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {result.highlighted_skills.map((skill, i) => (
                        <span
                          key={i}
                          className="px-2.5 py-1 bg-blue-50 text-blue-700 text-xs font-medium rounded-lg border border-blue-100 flex items-center gap-1"
                        >
                          <CheckCircle2Icon className="w-3 h-3 text-blue-500" />
                          {skill}
                        </span>
                      ))}
                    </div>
                  </div>

                  {result.matched_skills.length > 0 && (
                    <div>
                      <span className="text-xs font-semibold text-gray-700 block mb-2">
                        Candidate Background Overlap:
                      </span>
                      <div className="flex flex-wrap gap-1.5">
                        {result.matched_skills.map((skill, i) => (
                          <span
                            key={i}
                            className="px-2.5 py-1 bg-green-50 text-green-700 text-xs font-medium rounded-lg border border-green-100"
                          >
                            ✓ {skill}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Bullet Points Modifications Card */}
              <div className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm space-y-4">
                <div className="flex items-center justify-between border-b border-gray-100 pb-3">
                  <h4 className="text-sm font-bold text-gray-900 flex items-center gap-2">
                    <Code2Icon className="w-4 h-4 text-indigo-600" />
                    Tailored Resume Bullet Points & Content Changes ({result.bullet_changes.length})
                  </h4>
                  <span className="text-xs text-gray-400">Targeted Enhancements</span>
                </div>

                <div className="space-y-3">
                  {result.bullet_changes.map((change, idx) => (
                    <div
                      key={idx}
                      className="p-4 rounded-xl border border-gray-100 bg-gray-50/50 space-y-2 text-xs"
                    >
                      {change.reason && (
                        <div className="text-[11px] font-semibold text-indigo-700 flex items-center gap-1">
                          <ArrowRightIcon className="w-3 h-3" />
                          {change.reason}
                        </div>
                      )}
                      <div className="space-y-1.5">
                        <div className="text-gray-500">
                          <span className="font-semibold text-gray-600">Original:</span>{" "}
                          <span className="line-through">{change.original}</span>
                        </div>
                        <div className="text-gray-900 font-medium bg-white p-2.5 rounded-lg border border-gray-200">
                          <span className="font-semibold text-blue-700">Tailored:</span>{" "}
                          {change.tailored}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Bottom Download Banner */}
                <div className="p-4 rounded-xl bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-100 flex items-center justify-between mt-4">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-blue-600 text-white rounded-lg">
                      <FileTextIcon className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="text-xs font-bold text-gray-900">{result.filename}</div>
                      <div className="text-[11px] text-gray-500">
                        Verified 1-page PDF formatted cleanly
                      </div>
                    </div>
                  </div>

                  <button
                    onClick={handleDownloadPdf}
                    disabled={downloading}
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5 shadow-sm cursor-pointer disabled:opacity-50"
                  >
                    <DownloadIcon className="w-3.5 h-3.5" />
                    {downloading ? "Downloading..." : "Download Resume PDF"}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
