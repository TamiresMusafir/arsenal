const switchTheme = document.getElementById("darkModeSwitch");

if (switchTheme) {
    switchTheme.checked = document.body.classList.contains("dark-theme");

    switchTheme.addEventListener("change", () => {

        if (switchTheme.checked) {
            document.body.classList.add("dark-theme");
        } else {
            document.body.classList.remove("dark-theme");
        }

    });

}