// wizard.js — versão unificada (base: versão corrigida; sem duplicação de listeners)
document.addEventListener('DOMContentLoaded', function () {
const form = document.getElementById('wizardForm');
const nextBtn = document.getElementById('nextBtn');
const prevBtn = document.getElementById('prevBtn');
const steps = document.querySelectorAll('.wizard-step');
const contents = document.querySelectorAll('.wizard-content');
// Guarda: se a página não for a do wizard, não faz nada.
if (!form || !nextBtn || !prevBtn || contents.length === 0) return;
let current = 0;
let enviando = false;
function ehObrigatorio(campo) {
return campo.hasAttribute('required') || campo.classList.contains('required');
}
function updateWizard() {
contents.forEach(function (content, index) {
const ativo = index === current;
content.classList.toggle('active', ativo);
// Fallback: garante o passo a passo mesmo se o wizard.css não carregar.
content.style.display = ativo ? 'block' : 'none';
});
steps.forEach(function (step, index) {
step.classList.remove('active', 'completed');
if (index < current) step.classList.add('completed');
else if (index === current) step.classList.add('active');
});
prevBtn.classList.toggle('d-none', current === 0);
nextBtn.innerHTML = (current === contents.length - 1)
? '<i class="fa-solid fa-check me-1"></i> Finalizar'
: 'Próximo <i class="fa-solid fa-arrow-right ms-1"></i>';
}
// Valida apenas os campos do passo atual
function validateCurrentStep() {
const campos = contents[current].querySelectorAll('input, select, textarea');
let valido = true;
campos.forEach(function (campo) {
if (!ehObrigatorio(campo)) return;
const ok = campo.checkValidity();
campo.classList.toggle('is-invalid', !ok);
if (!ok) valido = false;
});
return valido;
}
function finalizar() {
if (enviando) return;
enviando = true;
nextBtn.disabled = true;
prevBtn.disabled = true;
nextBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-1"></i> Processando...';
const statusMsg = document.getElementById('statusMessage');
if (statusMsg) {
statusMsg.innerHTML = '<div class="alert alert-info">Enviando dados para processamento...</div>';
}
form.submit();
}
nextBtn.addEventListener('click', function () {
if (enviando) return;
if (!validateCurrentStep()) {
const primeiroInvalido = contents[current].querySelector('.is-invalid');
if (primeiroInvalido) {
primeiroInvalido.focus();
primeiroInvalido.scrollIntoView({ behavior: 'smooth', block: 'center' });
}
return;
}
if (current === contents.length - 1) {
finalizar();
return;
}
current++;
updateWizard();
});
prevBtn.addEventListener('click', function () {
if (enviando || current === 0) return;
current--;
updateWizard();
});
// Validação em tempo real — escopo restrito ao formulário
form.querySelectorAll('input, select, textarea').forEach(function (campo) {
const checar = function () {
if (!ehObrigatorio(this)) return;
this.classList.toggle('is-invalid', !this.checkValidity());
};
campo.addEventListener('blur', checar);
campo.addEventListener('input', checar);
});
// Enter avança em vez de submeter (exceto dentro de textarea)
form.addEventListener('keydown', function (e) {
if (e.key !== 'Enter') return;
if (e.target && e.target.tagName === 'TEXTAREA') return;
e.preventDefault();
nextBtn.click();
});
updateWizard();
});
