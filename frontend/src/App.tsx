import { useEffect, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./lib/auth";
import { AppShell } from "./components/AppShell";
import { LoadingBlock } from "./components/ui";
import { Landing } from "./pages/Landing";
import { Login } from "./pages/Login";
import { Home } from "./pages/Home";
import { CreatePlan } from "./pages/CreatePlan";
import { AgentIndex, AgentWorkspace } from "./pages/AgentWorkspace";
import { ProposalPage } from "./pages/ProposalPage";
import { Invitations } from "./pages/Invitations";
import { Room } from "./pages/Room";
import { Profile } from "./pages/Profile";
import { Verify } from "./pages/Verify";

function Private({ children }: { children: ReactNode }) {
  const { signedIn, isLoading } = useAuth();
  const location = useLocation();
  if (!signedIn) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (isLoading) return <AppShell><LoadingBlock label="Loading your account" /></AppShell>;
  return <>{children}</>;
}

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => { window.scrollTo(0, 0); }, [pathname]);
  return null;
}

export function App() {
  const { signedIn } = useAuth();
  return (
    <>
    <ScrollToTop />
    <Routes>
      <Route path="/" element={signedIn ? <Navigate to="/home" replace /> : <Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/home" element={<Private><Home /></Private>} />
      <Route path="/create" element={<Private><CreatePlan /></Private>} />
      <Route path="/agent" element={<Private><AgentIndex /></Private>} />
      <Route path="/plans/:planId" element={<Private><AgentWorkspace /></Private>} />
      <Route path="/proposals/:proposalId" element={<Private><ProposalPage /></Private>} />
      <Route path="/proposals/:proposalId/room" element={<Private><Room /></Private>} />
      <Route path="/invitations" element={<Private><Invitations /></Private>} />
      <Route path="/verify" element={<Private><Verify /></Private>} />
      <Route path="/profile" element={<Private><Profile /></Private>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </>
  );
}
