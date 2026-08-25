/**
 * Soft lockdown: monitora sinais de possível quebra de integridade da prova
 * SEM bloquear o aluno de continuar (por isso "soft"). Cada evento é
 * enviado ao backend via /attempts/{id}/integrity-event para revisão
 * posterior do professor.
 *
 * Sinais monitorados:
 * - Fullscreen API: saída do modo tela cheia
 * - Page Visibility API: troca de aba / minimização
 * - Bloqueio de atalhos comuns de cópia/impressão/devtools
 */

const Lockdown = (() => {
  let attemptId = null;
  let token = null;
  let onWarning = null;

  async function logEvent(eventType, detail) {
    if (!attemptId || !token) return;
    try {
      await fetch(`/attempts/${attemptId}/integrity-event`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ event_type: eventType, detail }),
      });
    } catch (err) {
      console.error("Falha ao registrar evento de integridade:", err);
    }
  }

  function requestFullscreen() {
    const el = document.documentElement;
    if (el.requestFullscreen) el.requestFullscreen().catch(() => {});
  }

  function handleVisibilityChange() {
    if (document.hidden) {
      logEvent("visibility_change", "Aluno saiu da aba/minimizou a janela");
      onWarning?.("Você saiu da tela da prova. Isso foi registrado.");
    }
  }

  function handleFullscreenChange() {
    if (!document.fullscreenElement) {
      logEvent("fullscreen_exit", "Aluno saiu do modo tela cheia");
      onWarning?.("Você saiu do modo tela cheia. Isso foi registrado.");
    }
  }

  const BLOCKED_COMBOS = [
    { key: "c", ctrl: true }, // copiar
    { key: "v", ctrl: true }, // colar
    { key: "p", ctrl: true }, // imprimir
    { key: "u", ctrl: true }, // ver código-fonte
    { key: "F12" },           // devtools
    { key: "F11" },           // sair de fullscreen nativo (opcional)
  ];

  function handleKeydown(e) {
    const match = BLOCKED_COMBOS.some(
      (c) =>
        e.key.toLowerCase() === c.key.toLowerCase() &&
        (!c.ctrl || e.ctrlKey || e.metaKey)
    );
    if (match) {
      e.preventDefault();
      logEvent("blocked_key", `${e.ctrlKey ? "Ctrl+" : ""}${e.key}`);
    }
  }

  function handleContextMenu(e) {
    e.preventDefault();
    logEvent("context_menu_blocked", null);
  }

  function start({ attemptId: id, token: tok, onWarning: warnCb }) {
    attemptId = id;
    token = tok;
    onWarning = warnCb;

    requestFullscreen();
    document.addEventListener("visibilitychange", handleVisibilityChange);
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    document.addEventListener("keydown", handleKeydown);
    document.addEventListener("contextmenu", handleContextMenu);
  }

  function stop() {
    document.removeEventListener("visibilitychange", handleVisibilityChange);
    document.removeEventListener("fullscreenchange", handleFullscreenChange);
    document.removeEventListener("keydown", handleKeydown);
    document.removeEventListener("contextmenu", handleContextMenu);
    if (document.fullscreenElement && document.exitFullscreen) {
      document.exitFullscreen().catch(() => {});
    }
  }

  return { start, stop };
})();
