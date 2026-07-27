// wizard.js - Lógica completa do wizard
document.addEventListener('DOMContentLoaded', function() {
  
  const steps = document.querySelectorAll(".wizard-step");
  const contents = document.querySelectorAll(".wizard-content");
  const nextBtn = document.getElementById("nextBtn");
  const prevBtn = document.getElementById("prevBtn");
  const form = document.getElementById("wizardForm");

  let current = 0;

  function updateWizard() {
    contents.forEach((content, index) => {
      content.classList.toggle("active", index === current);
    });

    steps.forEach((step, index) => {
      step.classList.remove("active", "completed");

      if (index < current) {
        step.classList.add("completed");
      } else if (index === current) {
        step.classList.add("active");
      }
    });

    if (current === 0) {
      prevBtn.classList.add("d-none");
    } else {
      prevBtn.classList.remove("d-none");
    }

    if (current === contents.length - 1) {
      nextBtn.innerHTML = '<i class="fa-solid fa-check me-1"></i> Finalizar';
    } else {
      nextBtn.innerHTML = 'Próximo <i class="fa-solid fa-arrow-right ms-1"></i>';
    }
  }

  // Validação do passo atual
  function validateCurrentStep() {
    const currentContent = contents[current];
    const fields = currentContent.querySelectorAll("input, select, textarea");
    let valid = true;

    fields.forEach(field => {
      if (field.hasAttribute('required') || field.classList.contains('required')) {
        if (!field.checkValidity()) {
          field.classList.add("is-invalid");
          valid = false;
        } else {
          field.classList.remove("is-invalid");
        }
      }
    });

    return valid;
  }

  // Botão Próximo
  nextBtn.addEventListener("click", function() {
    if (!validateCurrentStep()) {
      const firstInvalid = document.querySelector('.is-invalid');
      if (firstInvalid) {
        firstInvalid.focus();
        firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
      return;
    }

    if (current === contents.length - 1) {
      nextBtn.disabled = true;
      nextBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-1"></i> Processando...';
      
      const statusMsg = document.getElementById('statusMessage');
      if (statusMsg) {
        statusMsg.innerHTML = '<div class="alert alert-info">⏳ Enviando dados para processamento com IA...</div>';
      }
      
      form.submit();
      return;
    }

    current++;
    updateWizard();
  });

  // Botão Anterior
  prevBtn.addEventListener("click", function() {
    if (current > 0) {
      current--;
      updateWizard();
    }
  });

  // Atualiza o wizard inicial
  updateWizard();

  // Validação em tempo real nos campos
  document.querySelectorAll('input, select, textarea').forEach(field => {
    field.addEventListener('blur', function() {
      if (this.hasAttribute('required') || this.classList.contains('required')) {
        if (!this.checkValidity()) {
          this.classList.add('is-invalid');
        } else {
          this.classList.remove('is-invalid');
        }
      }
    });

    field.addEventListener('input', function() {
      if (this.hasAttribute('required') || this.classList.contains('required')) {
        if (!this.checkValidity()) {
          this.classList.add('is-invalid');
        } else {
          this.classList.remove('is-invalid');
        }
      }
    });
  });

  // Previne submissão acidental do formulário (Enter)
  form.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      nextBtn.click();
    }
  });

});
