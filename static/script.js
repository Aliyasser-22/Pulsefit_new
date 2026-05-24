const MOBILE_NAV_BREAKPOINT_PX = 720;

function initMobileNavigation() {
  const navBar = document.querySelector("header nav");
  const menuToggle = document.querySelector(".nav-toggle");
  const menu = document.querySelector(".nav-menu");

  if (!navBar || !menuToggle || !menu) {
    return;
  }

  function closeMobileMenu({ restoreFocus } = {}) {
    navBar.classList.remove("menu-open");
    menuToggle.setAttribute("aria-expanded", "false");

    if (restoreFocus) {
      menuToggle.focus();
    }
  }

  function openMobileMenu() {
    navBar.classList.add("menu-open");
    menuToggle.setAttribute("aria-expanded", "true");
    const firstLink = menu.querySelector("a");
    if (firstLink) {
      firstLink.focus();
    }
  }

  menuToggle.addEventListener("click", () => {
    const isOpen = navBar.classList.contains("menu-open");

    if (isOpen) {
      closeMobileMenu({ restoreFocus: true });
      return;
    }

    openMobileMenu();
  });

  menu.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", closeMobileMenu);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }

    if (navBar.classList.contains("menu-open")) {
      closeMobileMenu({ restoreFocus: true });
    }
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > MOBILE_NAV_BREAKPOINT_PX) {
      closeMobileMenu();
    }
  });
}

function initSmoothScrollToAnchors(stickyHeaderNav) {
  document.querySelectorAll('a[href^="#"]').forEach((link) => {
    link.addEventListener("click", (event) => {
      const targetSelector = link.getAttribute("href");

      if (!targetSelector || targetSelector === "#") {
        return;
      }

      const targetElement = document.querySelector(targetSelector);
      if (!targetElement) {
        return;
      }

      event.preventDefault();

      const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const headerOffset = stickyHeaderNav ? stickyHeaderNav.offsetHeight : 0;
      const scrollTop =
        targetElement.getBoundingClientRect().top + window.scrollY - headerOffset;

      window.scrollTo({
        top: Math.max(scrollTop, 0),
        behavior: prefersReducedMotion ? "auto" : "smooth",
      });
    });
  });
}

function initThemeToggle() {
  const themeToggle = document.getElementById('theme-toggle');
  if (!themeToggle) return;

  const currentTheme = localStorage.getItem('theme') || 'dark';
  document.body.classList.toggle('light', currentTheme === 'light');
  themeToggle.textContent = currentTheme === 'light' ? '☀️' : '🌙';

  themeToggle.addEventListener('click', () => {
    const isLight = document.body.classList.contains('light');
    document.body.classList.toggle('light');
    const newTheme = isLight ? 'dark' : 'light';
    localStorage.setItem('theme', newTheme);
    themeToggle.textContent = newTheme === 'light' ? '☀️' : '🌙';
  });
}

function initContactFormValidation() {
  const form = document.querySelector("#contact form");
  if (!form) {
    return;
  }

  const FULL_NAME_PATTERN = /^[A-Za-z\s'-]{3,}$/;
  const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  const formFields = [
    {
      input: form.querySelector("#name"),
      validate(trimmedValue) {
        if (!trimmedValue) {
          return { ok: false, message: "Full name is required." };
        }
        if (!FULL_NAME_PATTERN.test(trimmedValue)) {
          return { ok: false, message: "Please enter a valid full name." };
        }
        return { ok: true };
      },
    },
    {
      input: form.querySelector("#email"),
      validate(trimmedValue) {
        if (!trimmedValue) {
          return { ok: false, message: "Email address is required." };
        }
        if (!EMAIL_PATTERN.test(trimmedValue)) {
          return { ok: false, message: "Please enter a valid email address." };
        }
        return { ok: true };
      },
    },
    {
      input: form.querySelector("#message"),
      validate(trimmedValue) {
        if (!trimmedValue) {
          return { ok: false, message: "Message is required." };
        }
        if (trimmedValue.length < 10) {
          return { ok: false, message: "Message should be at least 10 characters." };
        }
        return { ok: true };
      },
    },
  ];

  function getOrCreateErrorElement(input) {
    const fieldRow = input.closest(".form-field") || input.closest("p");
    if (!fieldRow) {
      return null;
    }

    let errorElement = fieldRow.querySelector(".form-error");
    if (!errorElement) {
      errorElement = document.createElement("small");
      errorElement.className = "form-error";
      if (input.id) {
        errorElement.id = `${input.id}-error`;
      }
      fieldRow.append(errorElement);
    }
    return errorElement;
  }

  function showFieldError(input, message) {
    const errorElement = getOrCreateErrorElement(input);
    input.classList.add("is-invalid");
    input.setAttribute("aria-invalid", "true");
    if (errorElement) {
      errorElement.textContent = message;
      if (errorElement.id) {
        input.setAttribute("aria-describedby", errorElement.id);
      }
    }
  }

  function clearFieldError(input) {
    const errorElement = getOrCreateErrorElement(input);
    input.classList.remove("is-invalid");
    input.removeAttribute("aria-invalid");
    input.removeAttribute("aria-describedby");
    if (errorElement) {
      errorElement.textContent = "";
    }
  }

  function validateField(fieldConfig) {
    const { input, validate } = fieldConfig;
    if (!input) {
      return true;
    }

    const trimmedValue = input.value.trim();
    const result = validate(trimmedValue);

    if (!result.ok) {
      showFieldError(input, result.message);
      return false;
    }

    clearFieldError(input);
    return true;
  }

  formFields.forEach((fieldConfig) => {
    if (!fieldConfig.input) {
      return;
    }

    const runValidation = () => validateField(fieldConfig);
    fieldConfig.input.addEventListener("input", runValidation);
    fieldConfig.input.addEventListener("blur", runValidation);
  });

  form.addEventListener("submit", (event) => {
    const isFormValid = formFields.every((fieldConfig) => validateField(fieldConfig));
    if (!isFormValid) {
      event.preventDefault();
    }
  });
}

function init() {
  initMobileNavigation();

  const stickyHeaderNav = document.querySelector("header nav");
  initSmoothScrollToAnchors(stickyHeaderNav);

  initThemeToggle();

  initContactFormValidation();
}

init();
