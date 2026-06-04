/**
 * App.tsx — React Router v6 with protected routes.
 *
 * Silver requirement: real client-side routing with bookmarkable URLs.
 * Routes: /login, /lobby, /table/:id, /profile, /leaderboard
 * AuthGate: redirects to /login when session === null.
 */
import { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "framer-motion";
import { DEAL_SPRING } from "./motion/tokens";
import RouteFade from "./motion/presence/RouteFade";
import { useSession } from "./auth/supabase";
import Login from "./pages/Login";
import Lobby from "./pages/Lobby";
import BlackjackLobby from "./pages/BlackjackLobby";
import Table from "./pages/Table";
import Profile from "./pages/Profile";
import Leaderboard from "./pages/Leaderboard";
import PokerSetup from "./pages/PokerSetup";
import PokerTablePage from "./pages/PokerTablePage";
import HoldemLobby from "./pages/HoldemLobby";
import HoldemTablePage from "./pages/HoldemTablePage";
import HandHistory from "./pages/HandHistory";
import PaiGowLobby from "./pages/PaiGowLobby";
import PaiGowTablePage from "./pages/PaiGowTablePage";

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

/** Routes split into their own component so useLocation runs inside the router;
 *  RouteFade crossfades page content as the pathname changes. */
function AnimatedRoutes() {
  const location = useLocation();
  return (
    <RouteFade pathname={location.pathname}>
      <Routes location={location}>
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
            path="/blackjack"
            element={
              <AuthGate>
                <BlackjackLobby />
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

          {/* Texas Hold'em */}
          <Route
            path="/poker/setup"
            element={
              <AuthGate>
                <PokerSetup />
              </AuthGate>
            }
          />
          <Route
            path="/poker/table/:id"
            element={
              <AuthGate>
                <PokerTablePage />
              </AuthGate>
            }
          />

          {/* Multiplayer Hold'em */}
          <Route
            path="/holdem"
            element={
              <AuthGate>
                <HoldemLobby />
              </AuthGate>
            }
          />
          <Route
            path="/holdem/table/:id"
            element={
              <AuthGate>
                <HoldemTablePage />
              </AuthGate>
            }
          />

          <Route
            path="/history"
            element={
              <AuthGate>
                <HandHistory />
              </AuthGate>
            }
          />

          {/* Pai Gow Poker (additive — separate route surface) */}
          <Route
            path="/pai-gow/lobby"
            element={
              <AuthGate>
                <PaiGowLobby />
              </AuthGate>
            }
          />
          <Route
            path="/pai-gow/table/:id"
            element={
              <AuthGate>
                <PaiGowTablePage />
              </AuthGate>
            }
          />

          {/* Default redirect */}
          <Route path="/" element={<Navigate to="/lobby" replace />} />
          <Route path="*" element={<Navigate to="/lobby" replace />} />
      </Routes>
    </RouteFade>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <MotionConfig reducedMotion="user" transition={DEAL_SPRING}>
        <BrowserRouter>
          <AnimatedRoutes />
        </BrowserRouter>
      </MotionConfig>
    </QueryClientProvider>
  );
}
