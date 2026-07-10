import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useSessionStore } from "../store/sessionStore";
import { useAuthStore } from "../store/authStore";
import { getTurns, getRequirements, listAllSessions } from "../api/sessions";
import ProjectSidebar from "../components/Sidebar/ProjectSidebar";
import ChatPanel from "../components/Dialogue/ChatPanel";
import InputBox from "../components/Dialogue/InputBox";
import LiveRequirements from "../components/Requirements/LiveRequirements";
import ConflictResolutionPanel from "../components/Requirements/ConflictResolutionPanel";
import AppHeader from "../components/AppHeader";
import ResolutionVoteCard from "../components/Dialogue/ResolutionVoteCard";
import ResolutionRecordedCard from "../components/Dialogue/ResolutionRecordedCard";

// How often the RE's read-only interview view polls for the stakeholder's new
// messages + extracted requirements.
const POLL_MS = 6000;

export default function MainPage() {
  const [params] = useSearchParams();
  const sessionParam = params.get("session");
  const setActive = useSessionStore((s) => s.setActive);
  const activeId = useSessionStore((s) => s.activeId);
  // Narrow selector (kind only) so ProjectSidebar's periodic session refresh
  // doesn't re-render the whole page each poll.
  const activeSessionKind = useSessionStore(
    (s) => s.sessions.find((x) => x.id === s.activeId)?.kind
  );
  const setTurns = useSessionStore((s) => s.setTurns);
  const setRequirements = useSessionStore((s) => s.setRequirements);
  const role = useAuthStore((s) => s.role);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [activeKind, setActiveKind] = useState<string | null>(null);

  useEffect(() => {
    if (sessionParam) setActive(sessionParam);
  }, [sessionParam, setActive]);

  // For the RE, resolve which project this session belongs to so the header can
  // offer a "Back to project" link.
  useEffect(() => {
    if (role !== "requirements_engineer" || !activeId) return;
    let active = true;
    listAllSessions()
      .then((all) => {
        if (!active) return;
        const s = all.find((x) => x.id === activeId);
        if (s) {
          setProjectId(s.project_id);
          setActiveKind(s.kind ?? null);
        }
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [role, activeId]);

  const load = useCallback(
    async (alive: () => boolean) => {
      if (!activeId) return;
      try {
        const turns = await getTurns(activeId);
        if (alive()) setTurns(turns);
        if (role === "requirements_engineer") {
          const reqs = await getRequirements(activeId);
          if (alive()) setRequirements(reqs);
        }
      } catch {
        /* ignore */
      }
    },
    [activeId, role, setTurns, setRequirements]
  );

  useEffect(() => {
    let active = true;
    load(() => active);
    return () => { active = false; };
  }, [load]);

  // The RE observes the interview read-only, so poll for the stakeholder's new
  // turns + extracted requirements. Stakeholders are excluded: they post their
  // own messages with optimistic updates that a refetch would clobber.
  useEffect(() => {
    if (role !== "requirements_engineer" || !activeId) return;
    let active = true;
    const id = setInterval(() => {
      if (!document.hidden) load(() => active);
    }, POLL_MS);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [role, activeId, load]);

  return (
    <div className="grid h-screen grid-rows-[auto_1fr] bg-background">
      <AppHeader
        title="Probing Generator"
        backTo={
          role === "requirements_engineer" && projectId
            ? `/projects/${projectId}`
            : undefined
        }
        backLabel="Back to project"
      />
      {role === "requirements_engineer" ? (
        <div className="grid min-h-0 grid-cols-[248px_1fr_312px] grid-rows-[minmax(0,1fr)] overflow-hidden">
          <ProjectSidebar />
          <main className="flex min-h-0 flex-col overflow-hidden bg-surface-muted">
            <ChatPanel />
            <InputBox />
          </main>
          {activeKind === "conflict_resolution" && projectId && activeId ? (
            <ConflictResolutionPanel projectId={projectId} sessionId={activeId} />
          ) : (
            <LiveRequirements />
          )}
        </div>
      ) : (
        <div className="grid min-h-0 grid-cols-[248px_1fr] grid-rows-[minmax(0,1fr)] overflow-hidden">
          <ProjectSidebar />
          <main className="flex min-h-0 flex-col overflow-hidden bg-surface-muted">
            <ChatPanel />
            {/* Resolution cards fetch /sessions/{id}/resolution, which 404s for
                plain interviews — only mount them for conflict-resolution chats. */}
            {activeId && activeSessionKind === "conflict_resolution" && (
              <>
                <ResolutionRecordedCard sessionId={activeId} />
                <ResolutionVoteCard sessionId={activeId} />
              </>
            )}
            <InputBox />
          </main>
        </div>
      )}
    </div>
  );
}
