// Lanceur Windows de Bilan Ortho (double-clic -> app dans le navigateur).
//
// 1. Si le serveur local répond déjà : ouvre simplement le navigateur.
// 2. Sinon : ouvre aussitôt l'écran d'accueil (app/static/accueil.html, qui
//    bascule de lui-même sur l'application dès qu'elle répond), démarre le
//    serveur dans WSL (scripts/start-serveur.sh, silencieux) et signale un
//    serveur resté muet (60 s max).
//
// Compilé par packaging/windows/build.sh avec le csc.exe intégré à Windows
// (.NET Framework) — aucune dépendance à installer.

using System;
using System.Diagnostics;
using System.Net;
using System.Threading;
using System.Windows.Forms;

static class BilanOrtho
{
    const string Url = "http://127.0.0.1:8000";
    const string Distro = "Ubuntu";
    const string Depot = "/home/alexandre_delahaye/projects/bilan-ortho";
    const string Script = Depot + "/scripts/start-serveur.sh";
    // Fichier du dépôt vu depuis Windows (partage \\wsl.localhost).
    const string Accueil = "file://wsl.localhost/" + Distro + Depot + "/app/static/accueil.html?port=8000";

    static bool ServeurRepond()
    {
        try
        {
            var req = (HttpWebRequest)WebRequest.Create(Url + "/api/status");
            req.Timeout = 900;
            using (var resp = (HttpWebResponse)req.GetResponse())
                return (int)resp.StatusCode == 200;
        }
        catch { return false; }
    }

    static readonly string[] NavigateursApp = {
        @"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        @"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        @"C:\Program Files\Google\Chrome\Application\chrome.exe",
        @"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    };

    static void OuvrirNavigateur(string url)
    {
        // Fenêtre d'application dédiée (mode --app : ni onglets ni barre
        // d'adresse) ; repli sur le navigateur par défaut.
        foreach (var exe in NavigateursApp)
        {
            if (System.IO.File.Exists(exe))
            {
                Process.Start(new ProcessStartInfo(exe,
                    "--app=" + url + " --window-size=1280,860")
                { UseShellExecute = false });
                return;
            }
        }
        Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
    }

    [STAThread]
    static void Main()
    {
        if (ServeurRepond()) { OuvrirNavigateur(Url); return; }

        // Tout de suite : le navigateur se lance pendant que WSL et le serveur
        // démarrent, et l'écran d'accueil bascule sur l'app dès qu'elle répond.
        OuvrirNavigateur(Accueil);

        var psi = new ProcessStartInfo("wsl.exe",
            "-d " + Distro + " -- bash -lc \"" + Script + "\"")
        {
            CreateNoWindow = true,
            UseShellExecute = false,
            WindowStyle = ProcessWindowStyle.Hidden,
        };
        try { using (var p = Process.Start(psi)) p.WaitForExit(20000); }
        catch (Exception e)
        {
            MessageBox.Show("Impossible de démarrer WSL : " + e.Message,
                "Bilan Ortho", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }

        for (int i = 0; i < 240 && !ServeurRepond(); i++) Thread.Sleep(250);

        if (!ServeurRepond()) MessageBox.Show(
            "Le serveur n'a pas démarré dans le délai imparti.\n\n" +
            "Vérifiez le journal :\n\\\\wsl.localhost\\" + Distro +
            "\\home\\alexandre_delahaye\\.local\\share\\bilan-ortho\\serveur.log",
            "Bilan Ortho", MessageBoxButtons.OK, MessageBoxIcon.Warning);
    }
}
