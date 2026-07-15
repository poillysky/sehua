const loginForm = document.getElementById("loginForm");
const loginError = document.getElementById("loginError");
const loginSubmit = document.getElementById("loginSubmit");
const loginSubmitText = loginSubmit.querySelector(".login-submit-text");
const loginSubmitSpinner = loginSubmit.querySelector(".login-submit-spinner");
const togglePassword = document.getElementById("togglePassword");
const loginPassword = document.getElementById("loginPassword");

function showError(msg) {
  loginError.textContent = msg;
  loginError.hidden = !msg;
}

function setLoading(loading) {
  loginSubmit.disabled = loading;
  loginSubmitText.textContent = loading ? "登录中..." : "登 录";
  loginSubmitSpinner.hidden = !loading;
}

togglePassword.addEventListener("click", () => {
  const isPassword = loginPassword.type === "password";
  loginPassword.type = isPassword ? "text" : "password";
  togglePassword.querySelector(".icon-eye").hidden = isPassword;
  togglePassword.querySelector(".icon-eye-off").hidden = !isPassword;
  togglePassword.setAttribute("aria-label", isPassword ? "隐藏密码" : "显示密码");
  togglePassword.title = isPassword ? "隐藏密码" : "显示密码";
});

async function checkAlreadyLoggedIn() {
  try {
    const res = await fetch("/api/auth/status", { credentials: "include" });
    const data = await res.json();

    if (data.authenticated) {
      const next = new URLSearchParams(location.search).get("next") || "/";
      location.href = next;
      return;
    }
    if (!data.auth_required) {
      location.href = "/";
    }
  } catch {
    // ignore
  }
}

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  showError("");
  setLoading(true);

  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.getElementById("loginUsername").value.trim(),
        password: loginPassword.value,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || "登录失败");
    }
    const next = new URLSearchParams(location.search).get("next") || "/";
    location.href = next;
  } catch (err) {
    showError(err.message || "登录失败");
    loginPassword.select();
  } finally {
    setLoading(false);
  }
});

document.getElementById("loginUsername").focus();
checkAlreadyLoggedIn();
