/**
 * Módulo de acessibilidade:
 * - 7 níveis de fonte (até 54px)
 * - Alto contraste
 * - Audiodescrição via Web Speech API (leitura do enunciado da questão)
 *
 * Preferências são persistidas no backend (PATCH /auth/me/accessibility)
 * e aplicadas imediatamente na interface via classes no <html>.
 */

const Accessibility = (() => {
  let currentFontLevel = 1;
  let highContrast = false;
  let audioDescriptionEnabled = false;

  function applyFontLevel(level) {
    document.documentElement.classList.remove(
      ...[1, 2, 3, 4, 5, 6, 7].map((n) => `font-${n}`)
    );
    document.documentElement.classList.add(`font-${level}`);
    currentFontLevel = level;
  }

  function applyHighContrast(enabled) {
    document.documentElement.classList.toggle("high-contrast", enabled);
    highContrast = enabled;
  }

  function setAudioDescription(enabled) {
    audioDescriptionEnabled = enabled;
    if (!enabled) window.speechSynthesis?.cancel();
  }

  /** Lê em voz alta um texto (ex.: enunciado da questão atual). */
  function speak(text) {
    if (!audioDescriptionEnabled || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "pt-BR";
    utterance.rate = 0.95;
    window.speechSynthesis.speak(utterance);
  }

  async function persistPrefs(token, prefs) {
    await fetch("/auth/me/accessibility", {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(prefs),
    });
  }

  function init(userPrefs) {
    applyFontLevel(userPrefs.font_level || 1);
    applyHighContrast(!!userPrefs.high_contrast);
    setAudioDescription(!!userPrefs.audio_description);
  }

  return {
    init,
    applyFontLevel,
    applyHighContrast,
    setAudioDescription,
    speak,
    persistPrefs,
    get state() {
      return { currentFontLevel, highContrast, audioDescriptionEnabled };
    },
  };
})();
