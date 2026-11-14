import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { BriefcaseIcon, CheckCircleIcon, LayoutDashboardIcon, SettingsIcon, ListIcon, EyeIcon, EyeOffIcon, MenuIcon, XIcon } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import Dashboard from "./pages/Dashboard";
import Jobs from "./pages/Jobs";
import Applications from "./pages/Applications";
import ApprovalQueue from "./pages/ApprovalQueue";
import Settings from "./pages/Settings";
import { useAuthStore } from "./store/auth";
import { authApi, notificationsApi } from "./api/client";
import { useState } from "react";
import Interview from "./pages/Interview";
import InstantTailor from "./pages/InstantTailor";
import { BrainIcon, Wand2Icon } from "lucide-react";

const qc = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 60000,
    },
  },
});

function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    // Simulate API call (backend endpoint not yet implemented)
    await new Promise(resolve => setTimeout(resolve, 1200));
    setLoading(false);
    setSubmitted(true);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl border border-gray-200 p-8 w-full max-w-sm shadow-lg">
        <div className="flex items-center gap-2 mb-2">
          <BriefcaseIcon className="w-6 h-6 text-blue-600" />
          <h1 className="text-lg font-bold text-gray-900">Reset Password</h1>
        </div>
        <p className="text-sm text-gray-500 mb-6">
          Enter your email and we'll send you a reset link.
        </p>

        {submitted ? (
          <div className="bg-green-50 border border-green-200 rounded-xl p-5 text-center">
            <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-3">
              <CheckCircleIcon className="w-6 h-6 text-green-600" />
            </div>
            <p className="font-semibold text-green-800 text-sm">Check your inbox!</p>
            <p className="text-xs text-green-700 mt-1">
              If <strong>{email}</strong> is registered, you'll receive password reset instructions shortly.
            </p>
            <a href="/login" className="inline-block mt-4 text-xs text-blue-600 hover:underline font-medium">
              ← Back to Sign In
            </a>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email Address</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@example.com"
                className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 text-white py-2.5 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {loading ? "Sending..." : "Send Reset Link"}
            </button>
            <p className="text-xs text-center text-gray-400">
              Remembered?{" "}
              <a href="/login" className="text-blue-500 hover:underline">Sign in</a>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}

function LoginPage() {
  const { setAuth } = useAuthStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const res = await authApi.login(email, password);
      setAuth(res.data.access_token, res.data.user);
      window.location.href = "/";
    } catch {
      setError("Invalid email or password. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl border border-gray-200 p-8 w-full max-w-sm shadow-lg">
        <div className="flex items-center gap-2 mb-1">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
            <BriefcaseIcon className="w-5 h-5 text-white" />
          </div>
          <h1 className="text-lg font-bold text-gray-900">Job Agent System</h1>
        </div>
        <p className="text-sm text-gray-500 mb-6">Welcome back! Sign in to your account.</p>

        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="you@example.com"
              className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-sm font-medium text-gray-700">Password</label>
              <a href="/forgot-password" className="text-xs text-blue-500 hover:text-blue-700 hover:underline">
                Forgot password?
              </a>
            </div>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="••••••••"
                className="w-full border border-gray-200 rounded-lg px-3 py-2.5 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600"
              >
                {showPassword ? <EyeOffIcon className="w-4 h-4" /> : <EyeIcon className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="remember"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
              className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <label htmlFor="remember" className="text-sm text-gray-600 cursor-pointer">
              Remember me
            </label>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2.5 rounded-lg flex items-center gap-2">
              <span className="text-red-500">⚠</span>
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 text-white py-2.5 rounded-lg text-sm font-semibold hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
          >
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </form>

        <p className="text-xs text-gray-400 mt-5 text-center">
          Don't have an account?{" "}
          <a href="/register" className="text-blue-500 hover:underline font-medium">
            Create account
          </a>
        </p>
      </div>
    </div>
  );
}

function RegisterPage() {
  const [form, setForm] = useState({ email: "", full_name: "", password: "" });
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (form.password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }
    setLoading(true);
    setError("");

    try {
      await authApi.register(form);
      window.location.href = "/login";
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(axiosErr?.response?.data?.detail ?? "Registration failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl border border-gray-200 p-8 w-full max-w-sm shadow-lg">
        <div className="flex items-center gap-2 mb-1">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
            <BriefcaseIcon className="w-5 h-5 text-white" />
          </div>
          <h1 className="text-lg font-bold text-gray-900">Create Account</h1>
        </div>
        <p className="text-sm text-gray-500 mb-6">Join Job Agent to automate your job search.</p>

        <form onSubmit={handleRegister} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Full Name</label>
            <input
              type="text"
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              required
              placeholder="John Doe"
              className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required
              placeholder="you@example.com"
              className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                required
                minLength={8}
                placeholder="Min. 8 characters"
                className="w-full border border-gray-200 rounded-lg px-3 py-2.5 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600"
              >
                {showPassword ? <EyeOffIcon className="w-4 h-4" /> : <EyeIcon className="w-4 h-4" />}
              </button>
            </div>
            <p className="text-xs text-gray-400 mt-1">Must be at least 8 characters</p>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2.5 rounded-lg">
              ⚠ {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 text-white py-2.5 rounded-lg text-sm font-semibold hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
          >
            {loading ? "Creating account..." : "Create Account"}
          </button>
        </form>

        <p className="text-xs text-gray-400 mt-5 text-center">
          Already have an account?{" "}
          <a href="/login" className="text-blue-500 hover:underline font-medium">Sign in</a>
        </p>
      </div>
    </div>
  );
}

function Layout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuthStore();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const { data: notifs } = useQuery({
    queryKey: ["notifs-unread"],
    queryFn: () => notificationsApi.list(true),
    refetchInterval: 60000,
  });

  const unreadCount = (notifs?.data ?? []).length;

  const nav = [
    { to: "/", icon: LayoutDashboardIcon, label: "Dashboard" },
    { to: "/jobs", icon: BriefcaseIcon, label: "Jobs" },
    { to: "/tailor", icon: Wand2Icon, label: "Tailor Resume" },
    { to: "/applications", icon: ListIcon, label: "Applications" },
    { to: "/approvals", icon: CheckCircleIcon, label: "Approvals" },
    { to: "/interview", icon: BrainIcon, label: "Interview" },
    { to: "/settings", icon: SettingsIcon, label: "Settings" },
  ];

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      {/* Desktop Sidebar */}
      <aside className="hidden lg:flex w-56 bg-white border-r border-gray-200 flex-col flex-shrink-0">
        <div className="flex items-center gap-2 p-5 border-b border-gray-100">
          <div className="w-7 h-7 bg-blue-600 rounded-lg flex items-center justify-center">
            <BriefcaseIcon className="w-4 h-4 text-white" />
          </div>
          <span className="font-bold text-gray-900 text-sm">Job Agent</span>
        </div>

        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {nav.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? "bg-blue-50 text-blue-700 font-medium"
                    : "text-gray-600 hover:bg-gray-100"
                }`
              }
            >
              <Icon className="w-4 h-4" />
              {label}
              {label === "Approvals" && unreadCount > 0 && (
                <span className="ml-auto bg-amber-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
                  {unreadCount}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-gray-100">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-7 h-7 bg-blue-100 rounded-full flex items-center justify-center text-blue-700 font-bold text-xs">
              {user?.full_name?.[0]?.toUpperCase() ?? "U"}
            </div>
            <div className="min-w-0">
              <p className="text-xs font-medium text-gray-800 truncate">{user?.full_name}</p>
              <p className="text-xs text-gray-400 truncate">{user?.email}</p>
            </div>
          </div>
          <button
            onClick={logout}
            className="text-xs text-red-500 hover:text-red-700 font-medium"
          >
            Sign out
          </button>
        </div>
      </aside>

      {/* Mobile Overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Mobile Sidebar Drawer */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-72 bg-white border-r border-gray-200 flex flex-col transform transition-transform duration-300 lg:hidden ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between p-5 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 bg-blue-600 rounded-lg flex items-center justify-center">
              <BriefcaseIcon className="w-4 h-4 text-white" />
            </div>
            <span className="font-bold text-gray-900 text-sm">Job Agent</span>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500"
          >
            <XIcon className="w-5 h-5" />
          </button>
        </div>

        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {nav.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 rounded-xl text-sm transition-colors ${
                  isActive
                    ? "bg-blue-50 text-blue-700 font-medium"
                    : "text-gray-600 hover:bg-gray-50"
                }`
              }
            >
              <Icon className="w-5 h-5" />
              {label}
              {label === "Approvals" && unreadCount > 0 && (
                <span className="ml-auto bg-amber-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
                  {unreadCount}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-gray-100">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-9 h-9 bg-blue-100 rounded-full flex items-center justify-center text-blue-700 font-bold text-sm">
              {user?.full_name?.[0]?.toUpperCase() ?? "U"}
            </div>
            <div className="min-w-0">
              <p className="text-sm font-medium text-gray-800 truncate">{user?.full_name}</p>
              <p className="text-xs text-gray-400 truncate">{user?.email}</p>
            </div>
          </div>
          <button
            onClick={logout}
            className="w-full text-left text-sm text-red-500 hover:text-red-700 font-medium py-1"
          >
            Sign out
          </button>
        </div>
      </aside>

      {/* Main Area */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        {/* Mobile Top Header */}
        <header className="lg:hidden flex items-center justify-between px-4 py-3 bg-white border-b border-gray-200 shrink-0">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2 rounded-lg hover:bg-gray-100 text-gray-600"
          >
            <MenuIcon className="w-5 h-5" />
          </button>
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-blue-600 rounded-md flex items-center justify-center">
              <BriefcaseIcon className="w-4 h-4 text-white" />
            </div>
            <span className="font-bold text-gray-900 text-sm">Job Agent</span>
          </div>
          <div className="relative">
            {unreadCount > 0 && (
              <span className="w-5 h-5 bg-amber-500 text-white text-xs rounded-full flex items-center justify-center">
                {unreadCount}
              </span>
            )}
            {unreadCount === 0 && <div className="w-5 h-5" />}
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-auto">
          {children}
        </main>

        {/* Mobile Bottom Navigation */}
        <nav className="lg:hidden flex items-center bg-white border-t border-gray-200 shrink-0 safe-area-pb">
          {nav.slice(0, 5).map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `flex-1 flex flex-col items-center py-2 px-1 text-xs transition-colors relative ${
                  isActive ? "text-blue-600" : "text-gray-500"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <div className={`p-1.5 rounded-lg relative ${isActive ? "bg-blue-50" : ""}`}>
                    <Icon className="w-5 h-5" />
                    {label === "Approvals" && unreadCount > 0 && (
                      <span className="absolute -top-1 -right-1 w-4 h-4 bg-amber-500 text-white text-[9px] rounded-full flex items-center justify-center font-bold">
                        {unreadCount}
                      </span>
                    )}
                  </div>
                  <span className="mt-0.5 text-[10px] font-medium leading-tight text-center">
                    {label === "Tailor Resume" ? "Tailor" : label}
                  </span>
                </>
              )}
            </NavLink>
          ))}
          {/* More button to open sidebar for other nav items */}
          <button
            onClick={() => setSidebarOpen(true)}
            className="flex-1 flex flex-col items-center py-2 px-1 text-xs text-gray-500"
          >
            <div className="p-1.5 rounded-lg">
              <MenuIcon className="w-5 h-5" />
            </div>
            <span className="mt-0.5 text-[10px] font-medium">More</span>
          </button>
        </nav>
      </div>
    </div>
  );
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore();
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route
            path="/*"
            element={
              <ProtectedRoute>
                <Layout>
                  <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/jobs" element={<Jobs />} />
                    <Route path="/tailor" element={<InstantTailor />} />
                    <Route path="/applications" element={<Applications />} />
                    <Route path="/approvals" element={<ApprovalQueue />} />
                    <Route path="/interview" element={<Interview />} />
                    <Route path="/settings" element={<Settings />} />
                  </Routes>
                </Layout>
              </ProtectedRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
