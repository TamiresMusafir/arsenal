const switchTheme = document.getElementById("darkModeSwitch");

if (switchTheme) {
    switchTheme.addEventListener("change", () => {
        if (switchTheme.checked) {
            document.body.classList.add("dark-theme");
        } else {
            document.body.classList.remove("dark-theme");
        }
    });
}
