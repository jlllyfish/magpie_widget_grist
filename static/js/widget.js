/* Magpie — widget.js
   Detecte si Magpie est charge comme widget custom dans une vue Grist
   (via l'API grist-plugin-api.js) et, si c'est le cas, recupere
   automatiquement l'identifiant du document courant.

   Necessite l'acces 'full' (et non 'none') car Magpie doit pouvoir
   appeler grist.docApi.getDocName() -- Grist affichera une demande
   d'autorisation a l'utilisateur au premier chargement du widget dans
   le document (bandeau "Donner l'acces complet"). */

window.MagpieWidget = {
  isWidget: false,
  docId: null,
  inGristContext: false, // true des que 'grist' existe, meme si l'acces echoue
  ready: null, // Promise resolue une fois la detection terminee
};

(function () {
  // grist-plugin-api.js expose un objet global 'grist'. S'il est absent
  // ou si l'appel echoue (page ouverte hors iframe Grist), on retombe
  // silencieusement sur le mode webapp classique.
  if (typeof grist === 'undefined') {
    window.MagpieWidget.ready = Promise.resolve();
    return;
  }

  window.MagpieWidget.inGristContext = true;

  window.MagpieWidget.ready = new Promise((resolve) => {
    try {
      // 'full' est necessaire pour que getDocName() fonctionne. Grist
      // demandera confirmation a l'utilisateur avant d'accorder cet acces.
      // Niveau d'acces fixe cote serveur (GRIST_WIDGET_ACCESS), jamais
      // superieur a 'full'. Toute valeur inattendue retombe sur 'full'.
      const requested = document.body.dataset.widgetAccess;
      const access = requested === 'read table' ? 'read table' : 'full';
      grist.ready({ requiredAccess: access });

      // Un timeout de securite : si Grist ne repond pas (page chargee
      // hors iframe malgre la presence du script, ou acces refuse par
      // l'utilisateur), on ne bloque jamais l'application plus de 1.5s.
      const timeout = setTimeout(() => {
        window.MagpieWidget.isWidget = false;
        resolve();
      }, 1500);

      grist.docApi.getDocName()
        .then((docId) => {
          clearTimeout(timeout);
          if (docId) {
            window.MagpieWidget.isWidget = true;
            window.MagpieWidget.docId = docId;
          }
          resolve();
        })
        .catch(() => {
          clearTimeout(timeout);
          resolve();
        });
    } catch (e) {
      // grist.ready() peut lever une exception si appele hors contexte
      // widget valide -- on l'ignore et on continue en mode webapp.
      window.MagpieWidget.ready = Promise.resolve();
      resolve();
    }
  });
})();
