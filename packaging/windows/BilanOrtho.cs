// Lanceur Windows de Bilan Ortho (double-clic -> app dans le navigateur).
//
// 1. Si le serveur local répond déjà : ouvre simplement le navigateur.
// 2. Sinon : démarre le serveur dans WSL (scripts/start-serveur.sh, silencieux),
//    attend qu'il réponde (60 s max), puis ouvre le navigateur.
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
    const string Script = "/home/alexandre_delahaye/projects/bilan-ortho/scripts/start-serveur.sh";

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

    static void OuvrirNavigateur()
    {
        Process.Start(new ProcessStartInfo(Url) { UseShellExecute = true });
    }

    [STAThread]
    static void Main()
    {
        if (ServeurRepond()) { OuvrirNavigateur(); return; }

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

        for (int i = 0; i < 120 && !ServeurRepond(); i++) Thread.Sleep(500);

        if (ServeurRepond()) OuvrirNavigateur();
        else MessageBox.Show(
            "Le serveur n'a pas démarré dans le délai imparti.\n\n" +
            "Vérifiez le journal :\n\\\\wsl.localhost\\" + Distro +
            "\\home\\alexandre_delahaye\\.local\\share\\bilan-ortho\\serveur.log",
            "Bilan Ortho", MessageBoxButtons.OK, MessageBoxIcon.Warning);
    }
}
