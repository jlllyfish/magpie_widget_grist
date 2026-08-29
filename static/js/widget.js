/* Magpie — widget.js
   Detecte si Magpie est charge comme widget custom dans une vue Grist
   (via l'API grist-plugin-api.js) et, si c'est le cas, recupere
   automatiquement l'identifiant du document courant.

   Hors contexte widget (acces direct par navigateur, comme aujourd'hui
   sur Railway), ce script ne fait rien -- le reste de l'application
   continue de fonctionner exactement comme avant, avec le selecteur
   manuel organisation -> document. */

window.MagpieWidget = {
  isWidget: false,
  docId: null,
  ready: null, // Promise resolue une fois la detection terminee
};

(function () {
  console.log('[Magpie widget] Debut detection. typeof grist =', typeof grist);

  // grist-plugin-api.js expose un objet global 'grist'. S'il est absent
  // ou si l'appel echoue (page ouverte hors iframe Grist), on retombe
  // silencieusement sur le mode webapp classique.
  if (typeof grist === 'undefined') {
    console.log('[Magpie widget] grist est undefined -- mode webapp classique');
    window.MagpieWidget.ready = Promise.resolve();
    return;
  }

  window.MagpieWidget.ready = new Promise((resolve) => {
    try {
      console.log('[Magpie widget] Appel grist.ready()...');
      // requiredAccess: 'none' -- Magpie n'a jamais besoin de lire les
      // donnees du document, uniquement de connaitre son identifiant.
      // Grist n'affichera donc aucune demande d'autorisation sur les
      // donnees a l'utilisateur.
      grist.ready({ requiredAccess: 'none' });
      console.log('[Magpie widget] grist.ready() appele sans exception.');

      // Un timeout de securite : si Grist ne repond pas (page chargee
      // hors iframe malgre la presence du script), on ne bloque jamais
      // l'application plus de 1.5s.
      const timeout = setTimeout(() => {
        console.warn('[Magpie widget] TIMEOUT apres 1.5s -- getDocName() n a jamais resolu.');
        window.MagpieWidget.isWidget = false;
        resolve();
      }, 1500);

      console.log('[Magpie widget] Appel grist.docApi.getDocName()...');
      grist.docApi.getDocName()
        .then((docId) => {
          console.log('[Magpie widget] getDocName() resolu avec :', docId);
          clearTimeout(timeout);
          if (docId) {
            window.MagpieWidget.isWidget = true;
            window.MagpieWidget.docId = docId;
          }
          resolve();
        })
        .catch((err) => {
          console.error('[Magpie widget] getDocName() a rejete :', err);
          clearTimeout(timeout);
          resolve();
        });
    } catch (e) {
      console.error('[Magpie widget] Exception lors de grist.ready() :', e);
      // grist.ready() peut lever une exception si appele hors contexte
      // widget valide -- on l'ignore et on continue en mode webapp.
      window.MagpieWidget.ready = Promise.resolve();
      resolve();
    }
  });
})();
