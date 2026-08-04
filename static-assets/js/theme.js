const switchTheme = document.getElementById("darkModeSwitch");

if (switchTheme) {

    // aplica estado inicial
    if (switchTheme.checked) {
        document.body.classList.add("dark-theme");
    }

    switchTheme.addEventListener("change", () => {

        const ativo = switchTheme.checked;

        if (ativo) {
            document.body.classList.add("dark-theme");
        } else {
            document.body.classList.remove("dark-theme");
        }

        fetch("/configuracoes/alterar-tema/", {
            method: "POST",
            headers: {
                "X-CSRFToken": getCookie("csrftoken"),
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                tema_escuro: ativo
            })
        })
        .then(response => response.json())
        .then(data => {
            console.log("Tema salvo:", data);
        });

    });
}

function getCookie(name) {

    let cookieValue = null;

    if (document.cookie) {
        const cookies = document.cookie.split(";");

        for (let cookie of cookies) {
            cookie = cookie.trim();
            if (cookie.startsWith(name + "=")) {
                cookieValue = decodeURIComponent(
                    cookie.substring(name.length + 1)
                );
                break;
            }
        }
    }

    return cookieValue;
}
