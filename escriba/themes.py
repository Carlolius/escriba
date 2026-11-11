"""Color themes for the web interface. Each one has a light and a dark
variant, used according to the light/dark setting, with the colors of the
original palette."""

DEFAULT = "escriba"
KEYS = ("bg", "card", "line", "soft", "text", "primary", "on_primary", "secondary", "accent",
        "positive", "negative", "warning", "info")
QUASAR = ("primary", "secondary", "accent", "positive", "negative", "warning", "info")

THEMES = {
    "escriba": {
        "name": "Escriba",
        "header": ("#1e1b4b", "#312e81", "#4f46e5"),
        "light": {"bg": "#f1f2fb", "card": "#ffffff", "line": "#e4e6f2", "soft": "#4b5563", "text": "#111827",
                  "primary": "#4f46e5", "on_primary": "#ffffff", "secondary": "#b45309", "accent": "#0369a1",
                  "positive": "#15803d", "negative": "#dc2626", "warning": "#b45309", "info": "#0369a1"},
        "dark": {"bg": "#0e0f1d", "card": "#1a1b2f", "line": "#2c2e48", "soft": "#aab0c6", "text": "#e5e7f0",
                 "primary": "#a5b4fc", "on_primary": "#1e1b4b", "secondary": "#fbbf24", "accent": "#38bdf8",
                 "positive": "#4ade80", "negative": "#f87171", "warning": "#fbbf24", "info": "#38bdf8"},
    },
    "gruvbox": {
        "name": "Gruvbox",
        "header": ("#1d2021", "#32302f", "#504945"),
        "light": {"bg": "#f2e5bc", "card": "#fbf1c7", "line": "#d5c4a1", "soft": "#665c54", "text": "#3c3836",
                  "primary": "#af3a03", "on_primary": "#fbf1c7", "secondary": "#b57614", "accent": "#076678",
                  "positive": "#79740e", "negative": "#9d0006", "warning": "#b57614", "info": "#076678"},
        "dark": {"bg": "#1d2021", "card": "#282828", "line": "#3c3836", "soft": "#a89984", "text": "#ebdbb2",
                 "primary": "#fabd2f", "on_primary": "#282828", "secondary": "#fe8019", "accent": "#83a598",
                 "positive": "#b8bb26", "negative": "#fb4934", "warning": "#fabd2f", "info": "#83a598"},
    },
    "tokyonight": {
        "name": "Tokyo Night",
        "header": ("#16161e", "#1a1b26", "#3d59a1"),
        "light": {"bg": "#e1e2e7", "card": "#f2f3f7", "line": "#c4c8da", "soft": "#4f5a8a", "text": "#3760bf",
                  "primary": "#2e7de9", "on_primary": "#ffffff", "secondary": "#9854f1", "accent": "#007197",
                  "positive": "#587539", "negative": "#c64343", "warning": "#8c6c3e", "info": "#007197"},
        "dark": {"bg": "#16161e", "card": "#1f2335", "line": "#292e42", "soft": "#a9b1d6", "text": "#c0caf5",
                 "primary": "#7aa2f7", "on_primary": "#1a1b26", "secondary": "#bb9af7", "accent": "#7dcfff",
                 "positive": "#9ece6a", "negative": "#f7768e", "warning": "#e0af68", "info": "#7dcfff"},
    },
    "catppuccin": {
        "name": "Catppuccin",
        "header": ("#11111b", "#1e1e2e", "#45475a"),
        "light": {"bg": "#e6e9ef", "card": "#eff1f5", "line": "#ccd0da", "soft": "#5c5f77", "text": "#4c4f69",
                  "primary": "#8839ef", "on_primary": "#eff1f5", "secondary": "#fe640b", "accent": "#04a5e5",
                  "positive": "#368a24", "negative": "#d20f39", "warning": "#b5730f", "info": "#1e66f5"},
        "dark": {"bg": "#181825", "card": "#1e1e2e", "line": "#313244", "soft": "#a6adc8", "text": "#cdd6f4",
                 "primary": "#cba6f7", "on_primary": "#1e1e2e", "secondary": "#fab387", "accent": "#89dceb",
                 "positive": "#a6e3a1", "negative": "#f38ba8", "warning": "#f9e2af", "info": "#89b4fa"},
    },
    "dracula": {
        "name": "Dracula",
        "header": ("#191a21", "#282a36", "#44475a"),
        "light": {"bg": "#f5f0dc", "card": "#fffbeb", "line": "#dcd6bf", "soft": "#6c664b", "text": "#1f1f1f",
                  "primary": "#644ac9", "on_primary": "#fffbeb", "secondary": "#a3144d", "accent": "#036a96",
                  "positive": "#14710a", "negative": "#cb3a2a", "warning": "#846e15", "info": "#036a96"},
        "dark": {"bg": "#21222c", "card": "#282a36", "line": "#44475a", "soft": "#bcc2dc", "text": "#f8f8f2",
                 "primary": "#bd93f9", "on_primary": "#282a36", "secondary": "#ff79c6", "accent": "#8be9fd",
                 "positive": "#50fa7b", "negative": "#ff5555", "warning": "#f1fa8c", "info": "#8be9fd"},
    },
    "nord": {
        "name": "Nord",
        "header": ("#2e3440", "#3b4252", "#52739b"),
        "light": {"bg": "#e5e9f0", "card": "#eceff4", "line": "#d8dee9", "soft": "#4c566a", "text": "#2e3440",
                  "primary": "#5e81ac", "on_primary": "#eceff4", "secondary": "#b4693f", "accent": "#4c7c98",
                  "positive": "#5f7a45", "negative": "#bf616a", "warning": "#a07a2c", "info": "#4c7c98"},
        "dark": {"bg": "#2e3440", "card": "#3b4252", "line": "#434c5e", "soft": "#d8dee9", "text": "#eceff4",
                 "primary": "#88c0d0", "on_primary": "#2e3440", "secondary": "#d08770", "accent": "#81a1c1",
                 "positive": "#a3be8c", "negative": "#e08a92", "warning": "#ebcb8b", "info": "#81a1c1"},
    },
    "solarized": {
        "name": "Solarized",
        "header": ("#002b36", "#073642", "#586e75"),
        "light": {"bg": "#eee8d5", "card": "#fdf6e3", "line": "#d6cfb9", "soft": "#586e75", "text": "#073642",
                  "primary": "#268bd2", "on_primary": "#fdf6e3", "secondary": "#cb4b16", "accent": "#2aa198",
                  "positive": "#6c7c00", "negative": "#dc322f", "warning": "#957000", "info": "#268bd2"},
        "dark": {"bg": "#002b36", "card": "#073642", "line": "#174652", "soft": "#93a1a1", "text": "#eee8d5",
                 "primary": "#268bd2", "on_primary": "#fdf6e3", "secondary": "#cb4b16", "accent": "#2aa198",
                 "positive": "#859900", "negative": "#f05a57", "warning": "#b58900", "info": "#268bd2"},
    },
    "rosepine": {
        "name": "Rosé Pine",
        "header": ("#191724", "#26233a", "#403d52"),
        "light": {"bg": "#faf4ed", "card": "#fffaf3", "line": "#dfdad9", "soft": "#797593", "text": "#575279",
                  "primary": "#907aa9", "on_primary": "#fffaf3", "secondary": "#d7827e", "accent": "#56949f",
                  "positive": "#286983", "negative": "#b4637a", "warning": "#b9771f", "info": "#56949f"},
        "dark": {"bg": "#191724", "card": "#1f1d2e", "line": "#26233a", "soft": "#908caa", "text": "#e0def4",
                 "primary": "#c4a7e7", "on_primary": "#191724", "secondary": "#ebbcba", "accent": "#9ccfd8",
                 "positive": "#9ccfd8", "negative": "#eb6f92", "warning": "#f6c177", "info": "#9ccfd8"},
    },
    "everforest": {
        "name": "Everforest",
        "header": ("#232a2e", "#2d353b", "#475258"),
        "light": {"bg": "#f4f0d9", "card": "#fdf6e3", "line": "#e0dcc7", "soft": "#5c6a72", "text": "#4d5a61",
                  "primary": "#6d7d00", "on_primary": "#fdf6e3", "secondary": "#f57d26", "accent": "#3a94c5",
                  "positive": "#6d7d00", "negative": "#f85552", "warning": "#a57500", "info": "#3a94c5"},
        "dark": {"bg": "#272e33", "card": "#2d353b", "line": "#475258", "soft": "#9da9a0", "text": "#d3c6aa",
                 "primary": "#a7c080", "on_primary": "#2d353b", "secondary": "#e69875", "accent": "#7fbbb3",
                 "positive": "#a7c080", "negative": "#e67e80", "warning": "#dbbc7f", "info": "#7fbbb3"},
    },
}


def get(name):
    """The theme `name`, or the default one if it doesn't exist."""
    return THEMES.get(name) or THEMES[DEFAULT]


def _variables(colors):
    lines = [f"--escriba-{key.replace('_', '-')}: {colors[key]};" for key in KEYS]
    lines += [f"--q-{key}: {colors[key]} !important;" for key in QUASAR]  # NiceGUI sets them inline on <body>
    return " ".join(lines)


def css(name):
    """CSS variables of a theme, for both variants. The page's CSS uses them."""
    theme = get(name)
    dark = theme["dark"]
    h1, h2, h3 = theme["header"]
    return (f"body {{ {_variables(theme['light'])} "
            f"--escriba-header: linear-gradient(100deg, {h1} 0%, {h2} 45%, {h3} 100%); "
            # The recording card is always dark, like a recording studio's
            f"--escriba-stage: radial-gradient(120% 140% at 0% 0%, {dark['line']} 0%, {dark['card']} 55%, "
            f"{dark['bg']} 100%); --escriba-stage-text: {dark['text']}; --escriba-stage-soft: {dark['soft']}; "
            f"--escriba-stage-line: {dark['line']}; --escriba-system: {dark['primary']}; "
            f"--escriba-mic: {dark['warning']}; }}\n"
            f"body.body--dark {{ {_variables(dark)} --q-dark: {dark['card']}; --q-dark-page: {dark['bg']}; }}\n")
