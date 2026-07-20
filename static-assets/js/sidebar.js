document.addEventListener("DOMContentLoaded", () => {

    const btn = document.getElementById("mobileMenuBtn");
    const menu = document.querySelector(".sidebar");
    const close = document.querySelector(".close-menu");
    const backdrop = document.querySelector(".sidebar-backdrop");

    function abrirMenu() {
        menu.classList.add("open");
        backdrop.classList.add("show");
        document.body.classList.add("menu-open");
    }

    function fecharMenu() {
        menu.classList.remove("open");
        backdrop.classList.remove("show");
        document.body.classList.remove("menu-open");
    }

    btn.addEventListener("click", abrirMenu);
    close.addEventListener("click", fecharMenu);
    backdrop.addEventListener("click", fecharMenu);

});
