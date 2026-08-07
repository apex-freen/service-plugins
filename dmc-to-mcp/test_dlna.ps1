# DLNA DMR 测试脚本
# 用法: .\test_dlna.ps1 [设备IP]
# 示例: .\test_dlna.ps1 192.168.99.103

param(
    [string]$DeviceIP = "192.168.99.103"
)

$Port = 49152
$BaseUrl = "http://${DeviceIP}:$Port"
$Pass = 0
$Fail = 0

function Write-Result($name, $success, $detail = "") {
    if ($success) {
        Write-Host "[PASS] $name" -ForegroundColor Green
        $script:Pass++
    } else {
        Write-Host "[FAIL] $name" -ForegroundColor Red
        $script:Fail++
    }
    if ($detail) { Write-Host "       $detail" -ForegroundColor Gray }
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " DLNA DMR 测试脚本" -ForegroundColor Cyan
Write-Host " 设备: $DeviceIP`:$Port" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ========== 1. SSDP 发现（M-SEARCH） ==========
Write-Host "--- 1. SSDP 设备发现 (M-SEARCH) ---" -ForegroundColor Yellow

$ssdpMsg = "M-SEARCH * HTTP/1.1`r`nHOST: 239.255.255.250:1900`r`nMAN: `"ssdp:discover`"`r`nMX: 3`r`nST: urn:schemas-upnp-org:device:MediaRenderer:1`r`n`r`n"
$udp = New-Object System.Net.Sockets.UdpClient
$udp.Client.ReceiveTimeout = 5000
$udp.Connect("239.255.255.250", 1900)
$bytes = [System.Text.Encoding]::ASCII.GetBytes($ssdpMsg)
[void]$udp.Send($bytes, $bytes.Length)

$found = $false
$ssdpResponse = ""
try {
    $endpoint = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Any, 0)
    $respBytes = $udp.Receive([ref]$endpoint)
    $ssdpResponse = [System.Text.Encoding]::ASCII.GetString($respBytes)
    $found = $true
} catch {
    $found = $false
}
$udp.Close()

if ($found) {
    Write-Result "SSDP M-SEARCH 响应" $true
    # 提取 LOCATION
    if ($ssdpResponse -match "LOCATION:\s*(http://[^\r\n]+)") {
        Write-Result "LOCATION 头存在" $true $Matches[1]
    } else {
        Write-Result "LOCATION 头存在" $false "未找到 LOCATION"
    }
    # 提取 ST
    if ($ssdpResponse -match "ST:\s*(urn:[^\r\n]+)") {
        Write-Result "ST 头匹配 MediaRenderer" ($Matches[1] -match "MediaRenderer") $Matches[1]
    }
} else {
    Write-Result "SSDP M-SEARCH 响应" $false "5秒内未收到响应"
}
Write-Host ""

# ========== 2. device.xml ==========
Write-Host "--- 2. 设备描述 (device.xml) ---" -ForegroundColor Yellow
try {
    $resp = curl.exe -s --max-time 10 "$BaseUrl/device.xml"
    if ($resp -match "MediaRenderer" -and $resp -match "deviceType") {
        Write-Result "device.xml 返回 MediaRenderer" $true
    } else {
        Write-Result "device.xml 返回 MediaRenderer" $false "响应中未找到 MediaRenderer"
    }
    if ($resp -match "AVTransport") { Write-Result "AVTransport 服务" $true } else { Write-Result "AVTransport 服务" $false }
    if ($resp -match "RenderingControl") { Write-Result "RenderingControl 服务" $true } else { Write-Result "RenderingControl 服务" $false }
    if ($resp -match "ConnectionManager") { Write-Result "ConnectionManager 服务" $true } else { Write-Result "ConnectionManager 服务" $false }
    if ($resp -match "UDN>uuid:([^<]+)") { Write-Result "UDN UUID" $true $Matches[1] } else { Write-Result "UDN UUID" $false }
} catch {
    Write-Result "device.xml 请求" $false $_.Exception.Message
}
Write-Host ""

# ========== 3. SCPD 服务描述 ==========
Write-Host "--- 3. SCPD 服务描述 ---" -ForegroundColor Yellow
foreach ($svc in @("AVTransport", "RenderingControl", "ConnectionManager")) {
    try {
        $resp = curl.exe -s --max-time 10 "$BaseUrl/$svc/scpd.xml"
        if ($resp -match "scpd" -and $resp -match "actionList") {
            Write-Result "$svc/scpd.xml" $true
        } else {
            Write-Result "$svc/scpd.xml" $false "响应格式不正确"
        }
    } catch {
        Write-Result "$svc/scpd.xml" $false $_.Exception.Message
    }
}
Write-Host ""

# ========== 4. SOAP: GetTransportInfo ==========
Write-Host "--- 4. SOAP: GetTransportInfo ---" -ForegroundColor Yellow
$body = '<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:GetTransportInfo xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID></u:GetTransportInfo></s:Body></s:Envelope>'
$soapAction = '"urn:schemas-upnp-org:service:AVTransport:1#GetTransportInfo"'
try {
    $resp = curl.exe -s --max-time 10 -X POST "$BaseUrl/AVTransport/control" -H "Content-Type: text/xml; charset=utf-8" -H "SOAPACTION: $soapAction" -d $body
    if ($resp -match "GetTransportInfoResponse") {
        Write-Result "GetTransportInfo 响应" $true
        if ($resp -match "CurrentTransportState>([^<]+)") {
            Write-Result "播放状态" $true "CurrentTransportState = $($Matches[1])"
        }
    } else {
        Write-Result "GetTransportInfo 响应" $false $resp.Substring(0, [Math]::Min(200, $resp.Length))
    }
} catch {
    Write-Result "GetTransportInfo 请求" $false $_.Exception.Message
}
Write-Host ""

# ========== 5. SOAP: GetPositionInfo ==========
Write-Host "--- 5. SOAP: GetPositionInfo ---" -ForegroundColor Yellow
$body = '<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:GetPositionInfo xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID></u:GetPositionInfo></s:Body></s:Envelope>'
$soapAction = '"urn:schemas-upnp-org:service:AVTransport:1#GetPositionInfo"'
try {
    $resp = curl.exe -s --max-time 10 -X POST "$BaseUrl/AVTransport/control" -H "Content-Type: text/xml; charset=utf-8" -H "SOAPACTION: $soapAction" -d $body
    if ($resp -match "GetPositionInfoResponse") {
        Write-Result "GetPositionInfo 响应" $true
    } else {
        Write-Result "GetPositionInfo 响应" $false $resp.Substring(0, [Math]::Min(200, $resp.Length))
    }
} catch {
    Write-Result "GetPositionInfo 请求" $false $_.Exception.Message
}
Write-Host ""

# ========== 6. SOAP: SetAVTransportURI ==========
Write-Host "--- 6. SOAP: SetAVTransportURI ---" -ForegroundColor Yellow
$body = '<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><CurrentURI>http://example.com/test.mp3</CurrentURI><CurrentURIMetaData></CurrentURIMetaData></u:SetAVTransportURI></s:Body></s:Envelope>'
$soapAction = '"urn:schemas-upnp-org:service:AVTransport:1#SetAVTransportURI"'
try {
    $resp = curl.exe -s --max-time 10 -X POST "$BaseUrl/AVTransport/control" -H "Content-Type: text/xml; charset=utf-8" -H "SOAPACTION: $soapAction" -d $body
    if ($resp -match "SetAVTransportURIResponse") {
        Write-Result "SetAVTransportURI 响应" $true
    } else {
        Write-Result "SetAVTransportURI 响应" $false $resp.Substring(0, [Math]::Min(200, $resp.Length))
    }
} catch {
    Write-Result "SetAVTransportURI 请求" $false $_.Exception.Message
}
Write-Host ""

# ========== 7. SOAP: GetVolume ==========
Write-Host "--- 7. SOAP: GetVolume ---" -ForegroundColor Yellow
$body = '<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:GetVolume xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"><InstanceID>0</InstanceID><Channel>Master</Channel></u:GetVolume></s:Body></s:Envelope>'
$soapAction = '"urn:schemas-upnp-org:service:RenderingControl:1#GetVolume"'
try {
    $resp = curl.exe -s --max-time 10 -X POST "$BaseUrl/RenderingControl/control" -H "Content-Type: text/xml; charset=utf-8" -H "SOAPACTION: $soapAction" -d $body
    if ($resp -match "GetVolumeResponse") {
        Write-Result "GetVolume 响应" $true
        if ($resp -match "CurrentVolume>(\d+)") {
            Write-Result "当前音量" $true "CurrentVolume = $($Matches[1])"
        }
    } else {
        Write-Result "GetVolume 响应" $false $resp.Substring(0, [Math]::Min(200, $resp.Length))
    }
} catch {
    Write-Result "GetVolume 请求" $false $_.Exception.Message
}
Write-Host ""

# ========== 8. SOAP: SetVolume ==========
Write-Host "--- 8. SOAP: SetVolume (设为50) ---" -ForegroundColor Yellow
$body = '<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetVolume xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"><InstanceID>0</InstanceID><Channel>Master</Channel><DesiredVolume>50</DesiredVolume></u:SetVolume></s:Body></s:Envelope>'
$soapAction = '"urn:schemas-upnp-org:service:RenderingControl:1#SetVolume"'
try {
    $resp = curl.exe -s --max-time 10 -X POST "$BaseUrl/RenderingControl/control" -H "Content-Type: text/xml; charset=utf-8" -H "SOAPACTION: $soapAction" -d $body
    if ($resp -match "SetVolumeResponse") {
        Write-Result "SetVolume 响应" $true
    } else {
        Write-Result "SetVolume 响应" $false $resp.Substring(0, [Math]::Min(200, $resp.Length))
    }
} catch {
    Write-Result "SetVolume 请求" $false $_.Exception.Message
}
Write-Host ""

# ========== 9. SOAP: GetProtocolInfo ==========
Write-Host "--- 9. SOAP: GetProtocolInfo ---" -ForegroundColor Yellow
$body = '<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:GetProtocolInfo xmlns:u="urn:schemas-upnp-org:service:ConnectionManager:1"></u:GetProtocolInfo></s:Body></s:Envelope>'
$soapAction = '"urn:schemas-upnp-org:service:ConnectionManager:1#GetProtocolInfo"'
try {
    $resp = curl.exe -s --max-time 10 -X POST "$BaseUrl/ConnectionManager/control" -H "Content-Type: text/xml; charset=utf-8" -H "SOAPACTION: $soapAction" -d $body
    if ($resp -match "GetProtocolInfoResponse") {
        Write-Result "GetProtocolInfo 响应" $true
        if ($resp -match "audio/mpeg") {
            Write-Result "支持 audio/mpeg" $true
        }
    } else {
        Write-Result "GetProtocolInfo 响应" $false $resp.Substring(0, [Math]::Min(200, $resp.Length))
    }
} catch {
    Write-Result "GetProtocolInfo 请求" $false $_.Exception.Message
}
Write-Host ""

# ========== 汇总 ==========
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " 测试结果: $Pass 通过, $Fail 失败" -ForegroundColor $(if ($Fail -eq 0) { "Green" } else { "Red" })
Write-Host "========================================" -ForegroundColor Cyan
