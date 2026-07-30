const inputFoto = document.getElementById("id_foto");
const preview = document.getElementById("previewFoto");

if (inputFoto && preview) {
  inputFoto.addEventListener("change", function () {
    const arquivo = this.files[0];

    if (!arquivo) return;
    const reader = new FileReader();

    reader.onload = function (e) {
        preview.src = e.target.result;
    };
    
    reader.readAsDataURL(arquivo);
  });
}
