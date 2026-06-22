(function () {
  const appState = window.MeteoEventUI || {};

  function showToast(message, type = 'success') {
    if (type === 'error') {
      return;
    }

    let container = document.querySelector('.toast-container');
    if (!container) {
      container = document.createElement('div');
      container.className = 'toast-container';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast--${type}`;

    let emoji = 'ℹ️';
    if (type === 'success') emoji = '✅';
    if (type === 'error') emoji = '❌';

    toast.innerHTML = `
      <span class="toast__icon">${emoji}</span>
      <div class="toast__content"></div>
      <button class="toast__close" aria-label="Fermer">&times;</button>
      <div class="toast__progress"></div>
    `;
    toast.querySelector('.toast__content').textContent = message;
    container.appendChild(toast);

    const closeBtn = toast.querySelector('.toast__close');
    const dismiss = () => {
      if (!toast.parentNode) return;
      toast.style.animation = 'toast-slide-out 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards';
      toast.addEventListener('animationend', () => {
        toast.remove();
        if (container.children.length === 0) {
          container.remove();
        }
      });
    };

    closeBtn.addEventListener('click', dismiss);
    setTimeout(dismiss, 4000);
  }

  function renderFlashes() {
    const messages = Array.isArray(appState.flashes) ? appState.flashes : [];
    for (const item of messages) {
      if (!item || !item[0] || !item[1]) {
        continue;
      }
      const category = item[0];
      const message = item[1];
      if (category === 'error') {
        continue;
      }
      const type = category === 'error' ? 'error' : category === 'success' ? 'success' : 'info';
      showToast(message, type);
    }
  }

  function collectFormData(form, sendNotification) {
    const formData = new FormData();
    formData.append('send_notification', sendNotification ? '1' : '0');
    formData.append('message', document.getElementById('modal-message')?.value || '');

    form.querySelectorAll('input[type="hidden"]').forEach((input) => {
      if (input.name !== 'send_notification' && input.name !== 'message') {
        formData.append(input.name, input.value);
      }
    });

    return formData;
  }

  async function handleJsonAction(eventTarget, sendNotification) {
    const form = eventTarget.closest('form');
    if (!form) {
      return;
    }

    const action = form.getAttribute('action') || '';
    const sendNotificationButton = typeof sendNotification === 'boolean' ? sendNotification : eventTarget.dataset.sendNotification === '1';
    const targetForDelete = action.endsWith('/delete');
    const targetForNotify = action.endsWith('/notify');

    if (!targetForDelete && !targetForNotify) {
      let champNotification = form.querySelector('input[name="send_notification"]');
      if (!champNotification) {
        champNotification = document.createElement('input');
        champNotification.type = 'hidden';
        champNotification.name = 'send_notification';
        form.appendChild(champNotification);
      }

      let champMessage = form.querySelector('input[name="message"]');
      if (!champMessage) {
        champMessage = document.createElement('input');
        champMessage.type = 'hidden';
        champMessage.name = 'message';
        form.appendChild(champMessage);
      }

      champNotification.value = sendNotificationButton ? '1' : '0';
      champMessage.value = document.getElementById('modal-message')?.value || '';
      return form.submit();
    }

    try {
      const response = await fetch(action, {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        body: collectFormData(form, sendNotificationButton),
      });

      const data = await response.json();
      if (data.success) {
        showToast(data.message, 'success');

        if (targetForDelete) {
          const match = action.match(/\/events\/(\d+)\/delete/);
          const eventId = match ? match[1] : null;
          const card = eventId ? document.querySelector(`.carte[data-event-id="${eventId}"]`) : null;
          if (card) {
            card.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
            card.style.opacity = '0';
            card.style.transform = 'scale(0.9)';
            setTimeout(() => {
              card.remove();
              const grille = document.querySelector('.grille-evenements');
              if (grille) {
                const remainingCards = grille.querySelectorAll('.carte');
                if (remainingCards.length === 0) {
                  grille.style.display = 'none';
                  const vide = document.querySelector('.evenements-vide');
                  if (vide) {
                    vide.style.display = 'block';
                  }
                }
              }
            }, 300);
          }
        }
      } else {
        showToast(data.message || 'Une erreur est survenue.', 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Erreur de communication avec le serveur.', 'error');
    }
  }

  function setupModal() {
    const modal = document.getElementById('action-modal');
    const titre = document.getElementById('action-modal-title');
    const description = document.getElementById('action-modal-description');
    const btnSansMail = document.getElementById('action-modal-no-mail');
    const btnAvecMail = document.getElementById('action-modal-with-mail');
    const btnAnnuler = document.getElementById('action-modal-cancel');
    const emailHidden = document.getElementById('ev-destinataires');
    const emailError = document.getElementById('ev-destinataires-error');

    if (!modal || !titre || !description || !btnSansMail || !btnAvecMail || !btnAnnuler) {
      return;
    }

    let cible = null;

    const openModal = (trigger) => {
      cible = trigger.closest('form');
      titre.textContent = trigger.dataset.confirmTitle || 'Confirmer l\'action';
      description.textContent = trigger.dataset.confirmDescription || 'Voulez-vous confirmer cette action ?';

      const message = document.getElementById('modal-message');
      if (message) {
        message.value = '';
      }

      if (trigger.dataset.noMailHidden === 'true') {
        btnSansMail.style.display = 'none';
        btnAvecMail.textContent = 'Envoyer';
      } else {
        btnSansMail.style.display = 'inline-flex';
        btnAvecMail.textContent = 'Envoyer un mail';
      }

      modal.showModal();
    };

    const closeModal = () => {
      modal.close();
      cible = null;
    };

    const submit = (sendNotification) => {
      if (!cible) {
        return;
      }
      handleJsonAction(cible, sendNotification);
      closeModal();
    };

    document.querySelectorAll('[data-confirm-modal]').forEach((button) => {
      button.addEventListener('click', (event) => {
        event.preventDefault();
        if (emailHidden && emailError && !emailHidden.value) {
          return;
        }
        openModal(button);
      });
    });

    btnSansMail.addEventListener('click', () => submit(false));
    btnAvecMail.addEventListener('click', () => submit(true));
    btnAnnuler.addEventListener('click', closeModal);
  }

  function setupEmailChips() {
    const emailHidden = document.getElementById('ev-destinataires');
    const emailInput = document.getElementById('ev-destinataires-input');
    const emailChips = document.getElementById('email-chips');
    const emailError = document.getElementById('ev-destinataires-error');

    if (!emailHidden || !emailInput || !emailChips || !emailError) {
      return;
    }

    const champs = new Set();
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    const normaliser = (valeur) => (valeur || '').trim().toLowerCase();

    const definirErreur = () => {
      return;
    };

    const synchroniser = () => {
      emailHidden.value = Array.from(champs).join(', ');
    };

    const creerChip = (email) => {
      const chip = document.createElement('span');
      chip.className = 'email-chip';
      chip.dataset.email = email;
      chip.textContent = email;

      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'email-chip__remove';
      remove.textContent = '×';
      remove.addEventListener('click', () => {
        champs.delete(email);
        chip.remove();
        synchroniser();
        definirErreur('');
      });

      chip.appendChild(remove);
      emailChips.appendChild(chip);
    };

    const ajouterEmail = (raw) => {
      const email = normaliser(raw);
      if (!email) {
        emailInput.value = '';
        return;
      }
      if (!emailRegex.test(email)) {
        definirErreur('Email invalide. Format attendu : nom@domaine.extension (ex. nom@exemple.fr)');
        return;
      }
      if (champs.has(email)) {
        definirErreur('Cet email est déjà ajouté.');
        emailInput.value = '';
        return;
      }
      champs.add(email);
      creerChip(email);
      synchroniser();
      definirErreur('');
      emailInput.value = '';
    };

    (emailHidden.value || '')
      .split(/[,\n;]+/)
      .map(normaliser)
      .filter(Boolean)
      .forEach((email) => {
        if (emailRegex.test(email) && !champs.has(email)) {
          champs.add(email);
          creerChip(email);
        }
      });

    synchroniser();

    emailInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ' || event.key === ',') {
        event.preventDefault();
        if (emailInput.value.includes(',')) {
          emailInput.value.split(',').forEach((partie) => ajouterEmail(partie));
        } else {
          ajouterEmail(emailInput.value);
        }
      }

      if (event.key === 'Backspace' && emailInput.value === '') {
        const dernierChip = emailChips.querySelector('.email-chip:last-child');
        if (!dernierChip) {
          return;
        }
        const valeur = dernierChip.dataset.email;
        champs.delete(valeur);
        dernierChip.remove();
        synchroniser();
      }
    });

    emailInput.addEventListener('paste', (event) => {
      const texte = event.clipboardData?.getData('text') || '';
      if (!texte.includes(' ') && !texte.includes(',') && !texte.includes(';')) {
        return;
      }
      event.preventDefault();
      texte.split(/[,\s;]+/).forEach(ajouterEmail);
    });
  }

  async function changerDateEvenement(idEvenement, nouvelleDate) {
    try {
      const response = await fetch(`/events/${idEvenement}/date`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: new URLSearchParams({ date: nouvelleDate }),
      });

      const data = await response.json();
      if (data.success) {
        const card = document.querySelector(`.carte[data-event-id="${idEvenement}"]`);
        if (card) {
          const iconEl = card.querySelector('[data-meteo-icon]');
          const labelEl = card.querySelector('[data-meteo-label]');
          const dateEl = card.querySelector('[data-event-date]');
          const suggWrapper = card.querySelector('[data-suggestions-wrapper]');

          if (iconEl && data.event.html_icone_index) {
            iconEl.innerHTML = data.event.html_icone_index;
          }
          if (labelEl) {
            labelEl.textContent = data.event.meteo_icone_label;
          }
          if (dateEl) {
            dateEl.textContent = data.event.date_affichee;
            dateEl.setAttribute('datetime', data.event.date);
          }
          if (suggWrapper && data.event.html_suggestions_index) {
            suggWrapper.innerHTML = data.event.html_suggestions_index;
          }
        }

        const dateInput = document.getElementById('ev-date');
        const editMeteoBox = document.querySelector('[data-meteo-box]');
        const editSuggestions = document.getElementById('suggestions-date-container');

        if (dateInput) {
          dateInput.value = data.event.date;
        }
        if (editMeteoBox) {
          const editIcon = editMeteoBox.querySelector('[data-meteo-icon]');
          const editLabel = editMeteoBox.querySelector('[data-meteo-label]');
          if (editIcon && data.event.html_icone_edit) {
            editIcon.innerHTML = data.event.html_icone_edit;
          }
          if (editLabel) {
            editLabel.textContent = data.event.meteo_icone_label;
          }
        }
        if (editSuggestions && data.event.html_suggestions_edit) {
          editSuggestions.innerHTML = data.event.html_suggestions_edit;
        }

        showToast(data.message, 'success');
      } else {
        showToast(data.message || 'Une erreur est survenue.', 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Erreur de connexion au serveur.', 'error');
    }
  }

  window.changerDateEvenement = changerDateEvenement;

  document.addEventListener('DOMContentLoaded', () => {
    renderFlashes();
    setupModal();
    setupEmailChips();
  });
})();
