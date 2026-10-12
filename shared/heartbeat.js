// Signale au serveur que l'app est encore ouverte (fenêtre visible), peu importe la page.
// Si ces signaux s'arrêtent (fenêtre fermée, PC éteint/en veille, appli tuée...), le serveur
// considère l'utilisateur déconnecté et arrête le chrono en cours (voir server.py, /api/heartbeat).
(function () {
  function ping() {
    try {
      fetch('/api/heartbeat', { method: 'POST', keepalive: true }).catch(() => {});
    } catch (e) {
      // Pas grave si un ping échoue : le suivant rattrape, et le timeout côté serveur est tolérant.
    }
  }
  ping();
  setInterval(ping, 15000);
})();
