const switchTheme = document.getElementById("darkModeSwitch");

if (switchTheme.checked) {
    document.body.classList.add("dark-theme");
}

switchTheme?.addEventListener("change", () => {
    if (switchTheme.checked) {
        document.body.classList.add("dark-theme");
    } else {
        document.body.classList.remove("dark-theme");
    }
});
