/* ============================================================
   Learning Tracker — Motion Module
   GSAP-based page transitions, scroll animations, micro-interactions
   ============================================================ */

// ---- Load GSAP from CDN ----
(function loadGSAP() {
  if (window.gsap) return;
  const s = document.createElement('script');
  s.src = 'https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js';
  s.integrity = 'sha512-7eHR8cFzeEgp4oLs6Gx7VyFGLQH8R7oUKJmIu5im4DnGvMbKuC0l7IlhLTFmHN8D2A7kENiI6XHirBVwPpm6Qw==';
  s.crossOrigin = 'anonymous';
  s.onload = () => {
    // Load ScrollTrigger
    const st = document.createElement('script');
    st.src = 'https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/ScrollTrigger.min.js';
    st.integrity = 'sha512-3EF8sNqMYpDtKFmC+gR2KZEPgXqjMf2Hvy0g+U5eP/WTPgMKVMCjZvkMIA7s/D/0ldAkP3LdnVqBw4OaFTYs5Q==';
    st.crossOrigin = 'anonymous';
    st.onload = () => {
      gsap.registerPlugin(ScrollTrigger);
      document.dispatchEvent(new CustomEvent('gsap-ready'));
    };
    document.head.appendChild(st);
  };
  document.head.appendChild(s);
})();

// ---- Utility ----
const M = (function motion() {
  const isReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const defaults = { duration: 0.5, ease: 'power2.out' };

  // Wait for GSAP to load
  const ready = new Promise(resolve => {
    if (window.gsap) return resolve();
    document.addEventListener('gsap-ready', () => resolve(), { once: true });
    // Fallback: if GSAP never loads, resolve after 3s
    setTimeout(resolve, 3000);
  });

  return {
    ready,

    /** Animate element in from below with stagger */
    staggerIn(container, opts = {}) {
      if (isReduced) return;
      ready.then(() => {
        const items = container.querySelectorAll('[data-animate]');
        if (!items.length) return;
        gsap.from(items, {
          y: 24,
          opacity: 0,
          duration: opts.duration || 0.4,
          stagger: opts.stagger || 0.05,
          ease: 'power3.out',
          ...opts.extra,
        });
      });
    },

    /** Entrance animation for cards */
    cardIn(el, delay = 0) {
      if (isReduced) return;
      ready.then(() => {
        gsap.from(el, {
          y: 16,
          opacity: 0,
          scale: 0.98,
          duration: 0.35,
          delay,
          ease: 'back.out(1.4)',
        });
      });
    },

    /** Page/section entrance */
    sectionIn(el) {
      if (isReduced) return;
      ready.then(() => {
        gsap.from(el, { y: 20, opacity: 0, duration: 0.35, ease: 'power3.out' });
        // Animate children
        const children = el.querySelectorAll(':scope > *');
        if (children.length <= 1) return;
        gsap.from(children, {
          y: 14,
          opacity: 0,
          duration: 0.3,
          stagger: 0.04,
          ease: 'power2.out',
          delay: 0.1,
        });
      });
    },

    /** Count up animation for stat numbers */
    countUp(el, target) {
      if (isReduced) { el.textContent = target; return; }
      ready.then(() => {
        const num = parseInt(target) || 0;
        if (num === 0) { el.textContent = '0'; return; }
        // Handle "Xh Ym" format
        if (typeof target === 'string' && target.includes('h')) {
          el.textContent = target;
          return;
        }
        gsap.from(el, {
          textContent: 0,
          duration: 1.2,
          ease: 'power2.out',
          snap: { textContent: 1 },
          onUpdate: () => {
            const val = parseInt(el.textContent) || 0;
            el.textContent = val;
          },
          onComplete: () => { el.textContent = num; },
        });
      });
    },

    /** Progress bar animation */
    animateProgress(bar, target) {
      if (isReduced) { bar.style.width = target + '%'; return; }
      ready.then(() => {
        gsap.to(bar, { width: target + '%', duration: 0.8, ease: 'power3.out' });
      });
    },

    /** Pulse effect on save/action */
    pulse(el) {
      if (isReduced) return;
      ready.then(() => {
        gsap.fromTo(el, { scale: 1 }, { scale: 0.95, duration: 0.1, yoyo: true, repeat: 1, ease: 'power1.inOut' });
      });
    },

    /** Shake for error feedback */
    shake(el) {
      if (isReduced) return;
      ready.then(() => {
        gsap.fromTo(el, { x: 0 }, { x: 4, duration: 0.06, repeat: 5, yoyo: true, ease: 'none' });
      });
    },

    /** Sequential reveal for milestones */
    milestoneReveal(container) {
      if (isReduced) return;
      ready.then(() => {
        const sections = container.querySelectorAll('[data-animate-milestone]');
        if (!sections.length) return;
        gsap.from(sections, {
          y: 20,
          opacity: 0,
          duration: 0.35,
          stagger: 0.1,
          ease: 'power3.out',
          scrollTrigger: {
            trigger: container,
            start: 'top 80%',
            toggleActions: 'play none none none',
          },
        });
      });
    },
  };
})();

export { M };
