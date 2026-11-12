# Install Datavloot and start a new, empty project of your own, in one command:
#
#   powershell -ExecutionPolicy ByPass -c "irm https://datavloot.nl/new-project.ps1 | iex"
#
# No Python, git or admin rights needed. The script:
#   1. asks for the project's name; the project goes in %USERPROFILE%\<name>
#   2. installs uv (https://docs.astral.sh/uv/) for the current user, if missing
#   3. creates the project with `datavloot new`
#   4. gives it its own Python and packages (`uv sync`), and runs `dbt deps` and `dbt parse`
#   5. starts Dagster and the Crows Nest and opens http://localhost:8080
#
# The project starts empty: no sources or models yet. data-instructions.md in the
# project says how to add them. Running the script again with the same name starts
# the existing project; it never overwrites one.
#
# Settings, as environment variables (the one-liner takes no arguments):
#   DATAVLOOT_DIR      where the project goes, instead of asking for a name; the
#                      folder's name becomes the project's name
#   DATAVLOOT_VERSION  a toolkit version, e.g. 0.4.0 (default: the latest release)
#   DATAVLOOT_FROM     install the toolkit from here instead of PyPI, e.g. a checkout
#
# Written for Windows PowerShell 5.1, which every Windows 10 and 11 has.

# --- Shared by install-demo.ps1, new-project.ps1 and install-project.ps1 ---------
# Each script is served as one file (`irm | iex` fetches nothing else), so this
# part is repeated in all three. tests/test_install_scripts.py keeps them equal.

$PythonVersion = '3.12'
$DagsterPort = 3000
$CrowsNestPort = 8080

function Stop-Install([string]$Message) {
    throw "DATAVLOOT_STOP: $Message"
}

function Invoke-Step([string]$What, [scriptblock]$Command) {
    Write-Host ""
    Write-Host "==> $What" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Stop-Install "$What failed (exit code $LASTEXITCODE). The output above says why."
    }
}

function Test-Internet {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    try {
        Invoke-WebRequest -Uri 'https://pypi.org/simple/datavloot/' -Method Head `
            -UseBasicParsing -TimeoutSec 20 | Out-Null
    } catch {
        Stop-Install ("Cannot reach pypi.org: $($_.Exception.Message)`n" +
            "Check the internet connection. Behind a proxy, set HTTPS_PROXY " +
            "(for example `$env:HTTPS_PROXY = 'http://proxy:8080') and run this again.")
    }
}

function Install-Uv {
    $userBin = Join-Path $HOME '.local\bin'
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        if (Test-Path (Join-Path $userBin 'uv.exe')) {
            $env:Path = "$userBin;$env:Path"
        } else {
            # uv's own installer, for the current user: no admin rights. In a
            # process of its own, so whatever it does on exit stays there.
            Invoke-Step 'Installing uv' {
                powershell -NoProfile -ExecutionPolicy ByPass -Command `
                    "irm https://astral.sh/uv/install.ps1 | iex"
            }
            $env:Path = "$userBin;$env:Path"
            if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
                Stop-Install "uv was installed but is not found in $userBin. Open a new terminal and run this again."
            }
        }
    }
    Write-Host "uv: $(uv --version)"
}

function Get-PortUser([int]$Port) {
    # Who listens on the port, or $null when it is free. Asking Windows first:
    # binding 127.0.0.1 can succeed while another program listens on 0.0.0.0.
    try {
        $owner = (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
            Select-Object -First 1).OwningProcess
        try { return (Get-Process -Id $owner -ErrorAction Stop).ProcessName } catch { return "process $owner" }
    } catch {
        # None listening, or Get-NetTCPConnection is unavailable: try the port itself.
    }
    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        return $null
    } catch {
        return 'another program'
    } finally {
        if ($listener) { $listener.Stop() }
    }
}

function Assert-PortsFree {
    foreach ($entry in @(@($CrowsNestPort, 'the Crows Nest'), @($DagsterPort, 'Dagster'))) {
        $user = Get-PortUser $entry[0]
        if ($user) {
            Stop-Install ("Port $($entry[0]), which $($entry[1]) needs, is in use by $user.`n" +
                "If Datavloot is already running, open http://localhost:$CrowsNestPort. " +
                "Otherwise close that program and run this again.")
        }
    }
}

function Test-Project([string]$Dir) {
    (Test-Path (Join-Path $Dir 'dbt_project.yml')) -and (Test-Path (Join-Path $Dir 'pyproject.toml'))
}

function Test-ProjectDir([string]$Dir) {
    # $true when the folder holds a Datavloot project, $false when it is free.
    # An empty folder is removed: `datavloot demo` and `new` create it themselves.
    if (-not (Test-Path $Dir)) { return $false }
    if (Test-Project $Dir) { return $true }
    if (-not (Get-ChildItem -Force $Dir | Select-Object -First 1)) {
        Remove-Item $Dir
        return $false
    }
    Stop-Install ("'$Dir' already exists and is not a Datavloot project. " +
        "Nothing in it was changed. Set DATAVLOOT_DIR to another folder and run this again.")
}

function Get-ToolkitSource {
    if ($env:DATAVLOOT_FROM) { return $env:DATAVLOOT_FROM }
    if ($env:DATAVLOOT_VERSION) { return "datavloot[optimist]==$($env:DATAVLOOT_VERSION)" }
    return 'datavloot[optimist]@latest'
}

function Install-Environment {
    # In the project folder. Also repairs a project an earlier attempt left
    # halfway, and is quick when nothing is missing. An installed project gets
    # exactly the versions its maintainer locked.
    $locked = (Test-Path 'uv.lock') -and (Test-Path '.datavloot\install.json')
    Invoke-Step "Installing Python $PythonVersion and the project's packages" {
        if ($locked) { uv sync --python $PythonVersion --locked } else { uv sync --python $PythonVersion }
    }
    if (-not (Test-Path 'dbt_packages')) {
        Invoke-Step 'Installing the dbt packages' { uv run --no-sync dbt deps }
    }
    Invoke-Step 'Compiling the dbt project' { uv run --no-sync dbt parse }
}

function Write-StartHelp([string]$Dir) {
    Write-Host ""
    Write-Host "==> Starting Dagster and the Crows Nest" -ForegroundColor Cyan
    Write-Host "The Crows Nest opens at http://localhost:$CrowsNestPort. Keep this window open;"
    # The project's own datavloot rather than `uv run`: a window opened before
    # uv was installed does not have uv on its PATH yet.
    Write-Host "closing it or pressing Ctrl+C stops Datavloot. To start it again later, in PowerShell:"
    Write-Host "    cd `"$Dir`"; .venv\Scripts\datavloot start" -ForegroundColor Yellow
    Write-Host "Or have it start at every login, with a shortcut on the desktop and in the Start menu:"
    Write-Host "    cd `"$Dir`"; .venv\Scripts\datavloot autostart on" -ForegroundColor Yellow
    Write-Host "Or only the shortcut, without starting at login:"
    Write-Host "    cd `"$Dir`"; .venv\Scripts\datavloot shortcut on" -ForegroundColor Yellow
}

# --- End of the shared part -------------------------------------------------------

function Read-ProjectDir {
    if ($env:DATAVLOOT_DIR) { return [System.IO.Path]::GetFullPath($env:DATAVLOOT_DIR) }
    Write-Host "The project goes in a folder of that name in $HOME."
    while ($true) {
        $name = "$(Read-Host 'Name of the new project, for example harbor')".Trim()
        # The name becomes a Python package and a dbt project: letters, digits, - and _.
        if ($name -match '^[A-Za-z][A-Za-z0-9_-]*$') { return Join-Path $HOME $name }
        Write-Host "Use letters, digits, - and _, starting with a letter." -ForegroundColor Yellow
    }
}

function Install-Datavloot {
    Write-Host "Datavloot: installing the toolkit and a new, empty project" -ForegroundColor Cyan
    $dir = Read-ProjectDir
    $existing = Test-ProjectDir $dir

    Test-Internet
    Install-Uv

    if ($existing) {
        Write-Host ""
        Write-Host "Found a project in $dir; its files stay as they are."
    } else {
        $from = Get-ToolkitSource
        # Tells `datavloot new` not to print the steps this script takes itself.
        $env:DATAVLOOT_INSTALLER = '1'
        Invoke-Step "Creating the project in $dir" {
            uvx --python $PythonVersion --from $from datavloot new $dir
        }
    }

    Push-Location $dir
    try {
        Install-Environment
        Assert-PortsFree
        Write-StartHelp $dir
        if (-not $existing) {
            Write-Host "The project is empty: no sources or models yet. Start with data-instructions.md in"
            Write-Host "    $dir" -ForegroundColor Yellow
            Write-Host "or hand it to your AI assistant, then add your first source."
        }
        Write-Host ""
        uv run --no-sync datavloot start
    } finally {
        Pop-Location
    }
}

# Errors are reported here rather than with `exit`: under `irm | iex` in an open
# PowerShell window, `exit` would close that window.
try {
    Install-Datavloot
} catch {
    $message = $_.Exception.Message
    if ($message.StartsWith('DATAVLOOT_STOP: ')) {
        $message = $message.Substring('DATAVLOOT_STOP: '.Length)
    }
    Write-Host ""
    Write-Host "Error: $message" -ForegroundColor Red
    $global:LASTEXITCODE = 1
}
