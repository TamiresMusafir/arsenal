const switchTheme = document.getElementById("darkModeSwitch");

// Carrega a preferência salva
if (localStorage.getItem("tema") === "dark") {
    document.body.classList.add("dark-theme");

    if (switchTheme) {
        switchTheme.checked = true;
    }
}

// Quando clicar no switch
switchTheme?.addEventListener("change", () => {

  if (switchTheme.checked) {
      document.body.classList.add("dark-theme");
      localStorage.setItem("tema", "dark");
  } else {
      document.body.classList.remove("dark-theme");
      localStorage.setItem("tema", "light");
  }

});
