/**
 * App.tsx — React Router v6 with protected routes.
 *
 * Silver requirement: real client-side routing with bookmarkable URLs.
 * Routes: /login, /lobby, /table/:id, /profile, /leaderboard
 * AuthGate: redirects to /login when session === null.
 */
import { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useSession } from "./auth/supabase";
import Login from "./pages/Login";
import Lobby from "./pages/Lobby";
import Table from "./pages/Table";
import Profile from "./pages/Profile";
import Leaderboard from "./pages/Leaderboard";

// ─── QueryClient ─────────────────────────────────────────────────────────────

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 10_000,
    },
  },
});

// ─── Auth Gate ────────────────────────────────────────────────────────────────

interface AuthGateProps {
  children: React.ReactNode;
}

function AuthGate({ children }: AuthGateProps) {
  const { session, loading } = useSession();
  const navigate = useNavigate();

  // Listen for session-expired events from client.ts
  useEffect(() => {
    function handleExpired(): void {
      void navigate("/login");
    }
    window.addEventListener("betwise:session-expired", handleExpired);
    return () => window.removeEventListener("betwise:session-expired", handleExpired);
  }, [navigate]);

  if (loading) {
    return (
      <div className="min-h-screen bg-felt-green flex items-center justify-center">
        <span role="status" aria-busy="true" className="text-white animate-pulse">
          Loading…
        </span>
      </div>
    );
  }

  if (!session) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

// ─── Router ───────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* Public */}
          <Route path="/login" element={<Login />} />

          {/* Protected */}
          <Route
            path="/lobby"
            element={
              <AuthGate>
                <Lobby />
              </AuthGate>
            }
          />
          <Route
            path="/table/:id"
            element={
              <AuthGate>
                <Table />
              </AuthGate>
            }
          />
          <Route
            path="/profile"
            element={
              <AuthGate>
                <Profile />
              </AuthGate>
            }
          />
          <Route
            path="/leaderboard"
            element={
              <AuthGate>
                <Leaderboard />
              </AuthGate>
            }
          />

          {/* Default redirect */}
          <Route path="/" element={<Navigate to="/lobby" replace />} />
          <Route path="*" element={<Navigate to="/lobby" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
