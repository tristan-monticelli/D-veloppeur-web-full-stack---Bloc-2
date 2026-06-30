(function () {
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

  async function handleFormAction(form, sendNotification) {
    if (!form) {
      return;
    }

    const action = form.getAttribute('action') || '';
    const sendNotificationButton = Boolean(sendNotification);
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
      form.submit();
      return true;
    }

    try {
      const response = await fetch(action, {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        body: collectFormData(form, sendNotificationButton),
      });

      const data = await response.json();
      if (data.success) {
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
                  grille.classList.add('is-hidden');
                  const vide = document.querySelector('.evenements-vide');
                  if (vide) {
                    vide.classList.remove('is-hidden');
                  }
                }
              }
            }, 300);
          }
        }
        return true;
      }
    } catch (err) {
      return false;
    }
    return false;
  }

  async function handleDateAction(button, sendNotification) {
    const idEvenement = button.dataset.eventId;
    const nouvelleDate = button.dataset.eventDate;
    if (!idEvenement || !nouvelleDate) {
      return;
    }

    return changerDateEvenement(idEvenement, nouvelleDate, {
      sendNotification: Boolean(sendNotification),
      message: document.getElementById('modal-message')?.value || '',
    });
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

    const modalContent = modal.querySelector('.modal__content');
    let cible = null;
    let feedbackStartedAt = 0;
    let modalWidth = '';
    let modalHeight = '';
    let lastTrigger = null;

    const setFeedback = (state) => {
      if (!modalContent) {
        return;
      }

      if (state === 'loading') {
        feedbackStartedAt = Date.now();
      }

      modalContent.classList.add('modal__content--feedback');
      modalContent.style.width = modalWidth;
      modalContent.style.height = modalHeight;

      let feedback = modalContent.querySelector('.modal-feedback');
      if (!feedback) {
        feedback = document.createElement('div');
        feedback.className = 'modal-feedback';
        feedback.setAttribute('role', 'status');
        feedback.setAttribute('aria-live', 'polite');
        feedback.innerHTML = '<img class="modal-feedback__svg" src="/static/icons/email-validation.svg" alt="" aria-hidden="true"><span class="sr-only" data-feedback-text></span>';
        modalContent.appendChild(feedback);
      }
      feedback.dataset.state = state;
      const feedbackText = feedback.querySelector('[data-feedback-text]');
      if (feedbackText) {
        feedbackText.textContent = state === 'loading' ? 'Envoi en cours.' : 'Email envoyé.';
      }
    };

    const resetFeedback = () => {
      if (!modalContent) {
        return;
      }

      modalContent.classList.remove('modal__content--feedback');
      modalContent.style.width = '';
      modalContent.style.height = '';
      modalContent.querySelector('.modal-feedback')?.remove();
    };

    const openModal = (trigger) => {
      resetFeedback();
      lastTrigger = trigger;
      const form = trigger.closest('form');
      cible = trigger.hasAttribute('data-date-modal')
        ? { type: 'date', element: trigger }
        : { type: 'form', element: form };
      titre.textContent = trigger.dataset.modalTitle || 'Notification email';
      description.textContent = trigger.dataset.modalDescription || 'Voulez-vous envoyer un email aux destinataires ?';

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
      const rect = modalContent?.getBoundingClientRect();
      modalWidth = rect ? `${rect.width}px` : '';
      modalHeight = rect ? `${rect.height}px` : '';
      if (message && btnAvecMail.style.display !== 'none') {
        message.focus();
      } else {
        btnAvecMail.focus();
      }
    };

    const restoreFocus = (trigger) => {
      if (trigger && typeof trigger.focus === 'function' && document.contains(trigger)) {
        trigger.focus();
      }
      lastTrigger = null;
    };

    const closeModal = () => {
      const trigger = lastTrigger;
      cible = null;
      resetFeedback();
      if (modal.open) {
        modal.close();
      }
      restoreFocus(trigger);
    };

    const submit = async (sendNotification) => {
      if (!cible) {
        return;
      }

      if (!sendNotification) {
        if (cible.type === 'date') {
          handleDateAction(cible.element, false);
        } else {
          handleFormAction(cible.element, false);
        }
        closeModal();
        return;
      }

      setFeedback('loading');
      let success = false;
      if (cible.type === 'date') {
        success = await handleDateAction(cible.element, true);
      } else {
        success = await handleFormAction(cible.element, true);
      }
      if (success) {
        setFeedback('success');
        setTimeout(closeModal, Math.max(900, 2800 - (Date.now() - feedbackStartedAt)));
      } else {
        closeModal();
      }
    };

    document.addEventListener('click', (event) => {
      const button = event.target.closest('[data-confirm-modal], [data-date-modal]');
      if (!button) {
        return;
      }
      event.preventDefault();
      if (emailHidden && emailError && !emailHidden.value) {
        emailError.textContent = 'Ajoute au moins un destinataire avant de continuer.';
        return;
      }
      if (emailError) {
        emailError.textContent = '';
      }
      openModal(button);
    });

    btnSansMail.addEventListener('click', () => submit(false));
    btnAvecMail.addEventListener('click', () => submit(true));
    btnAnnuler.addEventListener('click', closeModal);
    modal.addEventListener('close', () => {
      if (cible || lastTrigger) {
        const trigger = lastTrigger;
        cible = null;
        resetFeedback();
        restoreFocus(trigger);
      }
    });
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

    const definirErreur = (message = '') => {
      emailError.textContent = message;
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
      remove.setAttribute('aria-label', `Retirer ${email}`);
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
        definirErreur('');
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

  async function changerDateEvenement(idEvenement, nouvelleDate, options = {}) {
    const params = new URLSearchParams({
      date: nouvelleDate,
      send_notification: options.sendNotification ? '1' : '0',
      message: options.message || '',
    });

    try {
      const response = await fetch(`/events/${idEvenement}/date`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: params,
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

        return true;
      }
    } catch (err) {
      return false;
    }
    return false;
  }

  window.changerDateEvenement = changerDateEvenement;

  document.addEventListener('DOMContentLoaded', () => {
    setupModal();
    setupEmailChips();
  });
})();
