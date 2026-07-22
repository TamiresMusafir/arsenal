const steps = document.querySelectorAll(".wizard-step");
const contents = document.querySelectorAll(".wizard-content");

const nextBtn = document.getElementById("nextBtn");
const prevBtn = document.getElementById("prevBtn");

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
    nextBtn.textContent = "Finalizar";
    nextBtn.type = "submit"; 
  } else {
    nextBtn.textContent = "Próximo";
    nextBtn.type = "button";
  }
}

nextBtn.addEventListener("click", () => {
  const currentContent = contents[current];
  const fields = currentContent.querySelectorAll("input,select,textarea");
  let valid = true;
  fields.forEach(field => {

    if (!field.checkValidity()) {
      field.classList.add("is-invalid");
      valid = false;
    } else {
      field.classList.remove("is-invalid");
    }
  });

  if (!valid) 
    return;
  if (current < contents.length - 1) {
    current++;
    updateWizard();
  } else {
    alert("Processo finalizado!");
  }
});

prevBtn.addEventListener("click", () => {
  if (current > 0) {
    current--;
    updateWizard();
  }
});

updateWizard();
