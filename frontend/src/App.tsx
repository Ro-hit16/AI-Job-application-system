import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, NavLink, Route, Routes } from "react-router-dom";
import { BriefcaseIcon, CheckCircleIcon, LayoutDashboardIcon, SettingsIcon, ListIcon } from "lucide-react";
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
import { BrainIcon } from "lucide-react";

const qc = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 60000,
    },
  },
});

function LoginPage() {
  const { setAuth } = useAuthStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
      setError("Invalid email or password");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="bg-white rounded-2xl border border-gray-200 p-8 w-full max-w-sm shadow-sm">
        <div className="flex items-center gap-2 mb-6">
          <BriefcaseIcon className="w-6 h-6 text-blue-600" />
          <h1 className="text-lg font-bold text-gray-900">
            Job Agent System
          </h1>
        </div>

        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Email
            </label>

            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Password
            </label>

            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {error && (
            <p className="text-red-500 text-sm">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </form>

        <p className="text-xs text-gray-400 mt-4 text-center">
          No account?{" "}
          <a
            href="/register"
            className="text-blue-500 hover:underline"
          >
            Register
          </a>
        </p>
      </div>
    </div>
  );
}

function RegisterPage() {
  const [form, setForm] = useState({
    email: "",
    full_name: "",
    password: "",
  });

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      await authApi.register(form);
      window.location.href = "/login";
    } catch (err: unknown) {
      const axiosErr = err as {
        response?: {
          data?: {
            detail?: string;
          };
        };
      };

      setError(
        axiosErr?.response?.data?.detail ??
          "Registration failed"
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="bg-white rounded-2xl border border-gray-200 p-8 w-full max-w-sm shadow-sm">
        <div className="flex items-center gap-2 mb-6">
          <BriefcaseIcon className="w-6 h-6 text-blue-600" />
          <h1 className="text-lg font-bold text-gray-900">
            Create Account
          </h1>
        </div>

        <form onSubmit={handleRegister} className="space-y-4">
          {(["full_name", "email", "password"] as const).map(
            (field) => (
              <div key={field}>
                <label className="block text-sm font-medium text-gray-700 mb-1 capitalize">
                  {field.replace("_", " ")}
                </label>

                <input
                  type={
                    field === "password"
                      ? "password"
                      : field === "email"
                      ? "email"
                      : "text"
                  }
                  value={form[field]}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      [field]: e.target.value,
                    })
                  }
                  required
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            )
          )}

          {error && (
            <p className="text-red-500 text-sm">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Creating..." : "Create Account"}
          </button>
        </form>

        <p className="text-xs text-gray-400 mt-4 text-center">
          Have an account?{" "}
          <a
            href="/login"
            className="text-blue-500 hover:underline"
          >
            Sign in
          </a>
        </p>
      </div>
    </div>
  );
}

function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, logout } = useAuthStore();

  const { data: notifs } = useQuery({
    queryKey: ["notifs-unread"],
    queryFn: () => notificationsApi.list(true),
    refetchInterval: 60000,
  });

  const unreadCount = (notifs?.data ?? []).length;

  const nav = [
    {
      to: "/",
      icon: LayoutDashboardIcon,
      label: "Dashboard",
    },
    {
      to: "/jobs",
      icon: BriefcaseIcon,
      label: "Jobs",
    },
    {
      to: "/applications",
      icon: ListIcon,
      label: "Applications",
    },
    {
      to: "/approvals",
      icon: CheckCircleIcon,
      label: "Approvals",
    },
    {
      to: "/interview",
      icon: BrainIcon,
      label: "Interview",
    },
    {
      to: "/settings",
      icon: SettingsIcon,
      label: "Settings",
    },
  ];

  return (
    <div className="flex h-screen bg-gray-50">
      <aside className="w-56 bg-white border-r border-gray-200 flex flex-col flex-shrink-0">
        <div className="flex items-center gap-2 p-5 border-b border-gray-100">
          <BriefcaseIcon className="w-5 h-5 text-blue-600" />
          <span className="font-bold text-gray-900 text-sm">
            Job Agent
          </span>
        </div>

        <nav className="flex-1 p-3 space-y-1">
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

              {label === "Approvals" &&
                unreadCount > 0 && (
                  <span className="ml-auto bg-amber-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
                    {unreadCount}
                  </span>
                )}
            </NavLink>
          ))}
        </nav>

        <div className="p-4 border-t border-gray-100">
          <p className="text-xs text-gray-500 mb-1 truncate">
            {user?.email}
          </p>

          <button
            onClick={logout}
            className="text-xs text-red-500 hover:text-red-700"
          >
            Sign out
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-auto">
        {children}
      </main>
    </div>
  );
}

function ProtectedRoute({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isAuthenticated } = useAuthStore();

  return isAuthenticated ? (
    <>{children}</>
  ) : (
    <Navigate to="/login" replace />
  );
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route
            path="/login"
            element={<LoginPage />}
          />

          <Route
            path="/register"
            element={<RegisterPage />}
          />

          <Route
            path="/*"
            element={
              <ProtectedRoute>
                <Layout>
                  <Routes>
                    <Route
                      path="/"
                      element={<Dashboard />}
                    />

                    <Route
                      path="/jobs"
                      element={<Jobs />}
                    />

                    <Route
                      path="/applications"
                      element={<Applications />}
                    />

                    <Route
                      path="/approvals"
                      element={<ApprovalQueue />}
                    />
                    <Route path="/interview" element={<Interview />} />

                    <Route
                      path="/settings"
                      element={<Settings />}
                    />
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
