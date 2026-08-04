document.addEventListener("DOMContentLoaded", () => {

    const btn = document.getElementById("mobileMenuBtn");
    const sidebar = document.querySelector(".sidebar");
    const close = document.querySelector(".close-menu");
    const backdrop = document.querySelector(".sidebar-backdrop");

    function abrirMenu() {
        sidebar.classList.add("open");
        backdrop.classList.add("show");
        document.body.classList.add("menu-open");
    }

    function fecharMenu() {
        sidebar.classList.remove("open");
        backdrop.classList.remove("show");
        document.body.classList.remove("menu-open");
    }

    btn?.addEventListener("click", abrirMenu);
    close?.addEventListener("click", fecharMenu);
    backdrop?.addEventListener("click", fecharMenu);

    const toggle = document.getElementById("perfilToggle");
    const menuPerfil = document.getElementById("menuPerfil");


    console.log(toggle);
    console.log(menuPerfil);

    if (toggle && menuPerfil) {

        toggle.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();

            menuPerfil.classList.toggle("show");
        });

        document.addEventListener("click", (e) => {
            if (!e.target.closest(".perfil")) {
                menuPerfil.classList.remove("show");
            }
        });

    }

});
