// src/pages/Interview.tsx
import { useState, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { interviewApi } from "../api/client";
import { BrainIcon, MicIcon, MicOffIcon, VolumeIcon, SendIcon, RotateCcwIcon } from "lucide-react";

type Phase = "setup" | "in_progress" | "complete";

export default function Interview() {
  const [phase, setPhase] = useState<Phase>("setup");
  const [sessionId, setSessionId] = useState("");
  const [techCount, setTechCount] = useState(5);
  const [hrCount, setHrCount] = useState(3);
  const [selectedJobId, setSelectedJobId] = useState("");
  const [customTitle, setCustomTitle] = useState("");
  const [customCompany, setCustomCompany] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [currentQuestion, setCurrentQuestion] = useState("");
  const [questionNumber, setQuestionNumber] = useState(1);
  const [totalQuestions, setTotalQuestions] = useState(0);
  const [remaining, setRemaining] = useState(0);
  const [transcript, setTranscript] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [evaluation, setEvaluation] = useState("");
  const [showEval, setShowEval] = useState(false);
  const [report, setReport] = useState<any>(null);

  const recognitionRef = useRef<any>(null);
  const synthRef = useRef(window.speechSynthesis);

  const { data: jobsData } = useQuery({
    queryKey: ["interview-jobs"],
    queryFn: () => interviewApi.jobs(),
  });
  const jobs: any[] = jobsData?.data ?? [];

  // Speak text using browser TTS
  const speak = (text: string, onEnd?: () => void) => {
    synthRef.current.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.rate = 0.95;
    utter.pitch = 1;
    utter.volume = 1;
    // Prefer a natural voice
    const voices = synthRef.current.getVoices();
    const preferred = voices.find(v =>
      v.name.includes("Google") || v.name.includes("Natural") || v.lang === "en-US"
    );
    if (preferred) utter.voice = preferred;
    utter.onstart = () => setIsSpeaking(true);
    utter.onend = () => { setIsSpeaking(false); onEnd?.(); };
    synthRef.current.speak(utter);
  };

  // Start speech recognition
  const startListening = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setError("Speech recognition not supported in your browser. Use Chrome.");
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onresult = (e: any) => {
      let final = "";
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) final += t;
        else interim += t;
      }
      setTranscript(prev => prev + final || interim);
    };

    recognition.onerror = (e: any) => {
      if (e.error !== "no-speech") setError(`Mic error: ${e.error}`);
      setIsListening(false);
    };

    recognition.onend = () => setIsListening(false);

    recognitionRef.current = recognition;
    recognition.start();
    setIsListening(true);
    setTranscript("");
  };

  const stopListening = () => {
    recognitionRef.current?.stop();
    setIsListening(false);
  };

  const toggleListening = () => {
    if (isListening) stopListening();
    else startListening();
  };

  const replayQuestion = () => speak(currentQuestion);

  const handleStart = async () => {
    setLoading(true);
    setError("");
    try {
      const payload: any = {
        technical_questions: techCount,
        hr_questions: hrCount,
      };
      if (selectedJobId) payload.job_id = selectedJobId;
      else {
        payload.job_title = customTitle || "Software Developer";
        payload.company = customCompany || "Tech Company";
      }
      const res = await interviewApi.start(payload);
      const data = res.data;
      setSessionId(data.session_id);
      const question = data.current_question?.question || data.message || "";
      setCurrentQuestion(question);
      setQuestionNumber(1);
      setTotalQuestions(data.total_questions);
      setRemaining(data.total_questions - 1);
      setPhase("in_progress");

      // Speak the first question after a short delay
      setTimeout(() => speak(question), 500);
    } catch (e: any) {
      setError(e.response?.data?.detail || "Failed to start interview");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmitAnswer = async () => {
    if (!transcript.trim()) {
      setError("Please speak your answer first.");
      return;
    }
    stopListening();
    setLoading(true);
    setError("");

    try {
      const res = await interviewApi.answer(sessionId, transcript);
      const data = res.data;
      const evalText = data.evaluation?.model_answer_hint || data.message || "";
      setEvaluation(evalText);
      setShowEval(true);

      // Speak the AI feedback
      speak(evalText, () => {
        if (data.is_complete) {
          setPhase("complete");
          interviewApi.report(sessionId).then(r => setReport(r.data)).catch(() => {});
        }
      });

      if (!data.is_complete && data.next_question) {
        const nextQ = data.next_question.question || "";
        setCurrentQuestion(nextQ);
        setQuestionNumber(data.next_question_number || questionNumber + 1);
        setRemaining(data.remaining || 0);
      }
    } catch (e: any) {
      setError(e.response?.data?.detail || "Failed to submit answer");
    } finally {
      setLoading(false);
    }
  };

  const handleNextQuestion = () => {
    setTranscript("");
    setEvaluation("");
    setShowEval(false);
    setTimeout(() => speak(currentQuestion), 300);
  };

  // ── SETUP ──────────────────────────────────────────────────────────────────
  if (phase === "setup") {
    return (
      <div className="p-6 max-w-2xl">
        <div className="flex items-center gap-3 mb-6">
          <div className="bg-blue-100 p-2 rounded-lg">
            <BrainIcon className="w-6 h-6 text-blue-600" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Voice Mock Interview</h1>
            <p className="text-sm text-gray-500">AI speaks questions — you answer aloud</p>
          </div>
        </div>

        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-4 text-sm text-blue-800">
          <strong>How it works:</strong> The AI will speak each question aloud. Press the microphone button to record your answer, then submit. Works best in Chrome.
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-4">
          <h2 className="font-semibold text-gray-800 mb-4">Choose a Job</h2>
          <select
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={selectedJobId}
            onChange={(e) => setSelectedJobId(e.target.value)}
          >
            <option value="">-- Enter manually below --</option>
            {jobs.map((j) => (
              <option key={j.id} value={j.id}>{j.title} @ {j.company}</option>
            ))}
          </select>
          {!selectedJobId && (
            <div className="grid grid-cols-2 gap-3">
              <input className="border border-gray-200 rounded-lg px-3 py-2 text-sm" placeholder="Job Title" value={customTitle} onChange={e => setCustomTitle(e.target.value)} />
              <input className="border border-gray-200 rounded-lg px-3 py-2 text-sm" placeholder="Company" value={customCompany} onChange={e => setCustomCompany(e.target.value)} />
            </div>
          )}
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-4">
          <h2 className="font-semibold text-gray-800 mb-4">Configuration</h2>
          <div className="grid grid-cols-2 gap-6">
            <div>
              <label className="block text-sm text-gray-700 mb-2">🔧 Technical: <strong>{techCount}</strong></label>
              <input type="range" min="2" max="10" value={techCount} onChange={e => setTechCount(Number(e.target.value))} className="w-full accent-blue-600" />
            </div>
            <div>
              <label className="block text-sm text-gray-700 mb-2">👥 HR: <strong>{hrCount}</strong></label>
              <input type="range" min="1" max="6" value={hrCount} onChange={e => setHrCount(Number(e.target.value))} className="w-full accent-purple-600" />
            </div>
          </div>
          <p className="text-sm text-gray-500 mt-3">Total: <strong>{techCount + hrCount} questions</strong></p>
        </div>

        {error && <p className="text-red-500 text-sm mb-3">{error}</p>}

        <button onClick={handleStart} disabled={loading} className="w-full bg-blue-600 text-white py-3 rounded-xl font-medium hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2">
          <BrainIcon className="w-5 h-5" />
          {loading ? "Preparing interview..." : "Start Voice Interview"}
        </button>
      </div>
    );
  }

  // ── IN PROGRESS ────────────────────────────────────────────────────────────
  if (phase === "in_progress") {
    const progress = ((questionNumber - 1) / totalQuestions) * 100;

    return (
      <div className="p-6 max-w-2xl">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <BrainIcon className="w-5 h-5 text-blue-600" />
            <span className="font-semibold text-gray-900">Voice Interview</span>
          </div>
          <span className="text-sm text-gray-500">Question {questionNumber} of {totalQuestions}</span>
        </div>

        <div className="w-full bg-gray-200 rounded-full h-1.5 mb-6">
          <div className="bg-blue-600 h-1.5 rounded-full transition-all duration-500" style={{ width: `${progress}%` }} />
        </div>

        {/* Question card */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 mb-4">
          <div className="flex items-start justify-between gap-3">
            <p className="text-gray-900 font-medium text-base leading-relaxed flex-1">{currentQuestion}</p>
            <button
              onClick={replayQuestion}
              disabled={isSpeaking}
              className="shrink-0 p-2 rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-40"
              title="Replay question"
            >
              <VolumeIcon className="w-4 h-4 text-gray-600" />
            </button>
          </div>
          {isSpeaking && (
            <p className="text-xs text-blue-500 mt-2 flex items-center gap-1">
              <span className="inline-block w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
              AI is speaking...
            </p>
          )}
        </div>

        {/* Voice recording */}
        {!showEval && (
          <div className="bg-white rounded-xl border border-gray-200 p-5 mb-4">
            <p className="text-sm font-medium text-gray-700 mb-4">Your Answer</p>

            {/* Big mic button */}
            <div className="flex flex-col items-center gap-3 mb-4">
              <button
                onClick={toggleListening}
                disabled={isSpeaking || loading}
                className={`w-20 h-20 rounded-full flex items-center justify-center transition-all ${
                  isListening
                    ? "bg-red-500 hover:bg-red-600 shadow-lg scale-110"
                    : "bg-blue-600 hover:bg-blue-700"
                } disabled:opacity-40`}
              >
                {isListening
                  ? <MicOffIcon className="w-8 h-8 text-white" />
                  : <MicIcon className="w-8 h-8 text-white" />
                }
              </button>
              <p className="text-sm text-gray-500">
                {isListening ? "🔴 Listening... tap to stop" : "Tap to start speaking"}
              </p>
            </div>

            {/* Live transcript */}
            <div className="bg-gray-50 rounded-lg p-3 min-h-[80px] mb-4">
              <p className="text-xs text-gray-400 mb-1">Live transcript</p>
              <p className="text-sm text-gray-800">{transcript || <span className="text-gray-400 italic">Your words will appear here as you speak...</span>}</p>
            </div>

            {error && <p className="text-red-500 text-sm mb-3">{error}</p>}

            <div className="flex gap-2">
              <button
                onClick={() => setTranscript("")}
                className="px-3 py-2 rounded-lg border border-gray-200 text-sm text-gray-600 hover:bg-gray-50 flex items-center gap-1"
              >
                <RotateCcwIcon className="w-4 h-4" /> Clear
              </button>
              <button
                onClick={handleSubmitAnswer}
                disabled={loading || !transcript.trim()}
                className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                <SendIcon className="w-4 h-4" />
                {loading ? "AI is evaluating..." : "Submit Answer"}
              </button>
            </div>
          </div>
        )}

        {/* AI feedback (spoken + shown) */}
        {showEval && evaluation && (
          <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 mb-4">
            <p className="text-sm font-medium text-blue-800 mb-2">
              {isSpeaking ? "🔊 AI Feedback (speaking...)" : "AI Feedback"}
            </p>
            <p className="text-sm text-blue-900 leading-relaxed">{evaluation}</p>

            {remaining > 0 ? (
              <button
                onClick={handleNextQuestion}
                className="mt-4 w-full bg-blue-600 text-white py-2.5 rounded-lg text-sm font-medium hover:bg-blue-700"
              >
                Next Question ({remaining} remaining) →
              </button>
            ) : (
              <button
                onClick={() => setPhase("complete")}
                className="mt-4 w-full bg-green-600 text-white py-2.5 rounded-lg text-sm font-medium hover:bg-green-700"
              >
                View Final Report 🎉
              </button>
            )}
          </div>
        )}
      </div>
    );
  }

  // ── COMPLETE ───────────────────────────────────────────────────────────────
  if (phase === "complete") {
    const overall = report?.scores?.overall ?? 0;
    return (
      <div className="p-6 max-w-2xl">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Interview Complete!</h1>
          <button onClick={() => { setPhase("setup"); setReport(null); setSessionId(""); setTranscript(""); setEvaluation(""); setShowEval(false); }} className="text-sm text-blue-600 hover:underline">
            Start New
          </button>
        </div>

        {report ? (
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <p className="text-sm text-gray-500">{report.job_title} @ {report.company}</p>
            <h2 className="text-4xl font-bold mt-1 text-blue-600">{overall}/10</h2>
            <p className="text-lg font-medium text-gray-700 mt-1">{report.verdict}</p>
            <p className="text-sm text-gray-500 mt-1">{report.hire_recommendation}</p>
            {report.executive_summary && (
              <p className="text-sm text-gray-600 mt-4 pt-4 border-t border-gray-100">{report.executive_summary}</p>
            )}
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-gray-200 p-6 text-center text-gray-500">
            Great job completing the interview! Your report is being generated...
          </div>
        )}
      </div>
    );
  }

  return <div className="p-6 text-gray-500">Loading...</div>;
}