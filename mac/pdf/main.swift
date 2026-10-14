// [Define404]
// 미팅냥 PDF 만들기: 표준입력으로 받은 HTML을 A4 PDF로 그려 지정한 경로에 저장한다.
// 사용: meet-pdf <저장할 경로.pdf> < page.html
import AppKit
import WebKit

guard CommandLine.arguments.count >= 2 else {
    FileHandle.standardError.write("사용: meet-pdf <out.pdf> < page.html\n".data(using: .utf8)!)
    exit(2)
}
let outURL = URL(fileURLWithPath: CommandLine.arguments[1])
let html = String(data: FileHandle.standardInput.readDataToEndOfFile(), encoding: .utf8) ?? ""

let app = NSApplication.shared
app.setActivationPolicy(.prohibited)

final class Renderer: NSObject, WKNavigationDelegate {
    let web: WKWebView
    let window: NSWindow

    override init() {
        // A4 폭(약 595pt)에 맞춘 화면에 그린다
        web = WKWebView(frame: NSRect(x: 0, y: 0, width: 595, height: 842))
        window = NSWindow(contentRect: web.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        super.init()
        window.contentView = web
        web.navigationDelegate = self
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        // 웹 글꼴이 다 그려질 시간을 조금 둔다
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { self.save() }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        FileHandle.standardError.write("불러오기 실패: \(error.localizedDescription)\n".data(using: .utf8)!)
        exit(1)
    }

    func save() {
        let info = NSPrintInfo()
        info.paperSize = NSSize(width: 595.28, height: 841.89)
        info.topMargin = 46; info.bottomMargin = 46; info.leftMargin = 0; info.rightMargin = 0
        info.horizontalPagination = .fit
        info.verticalPagination = .automatic
        info.jobDisposition = .save
        info.dictionary()[NSPrintInfo.AttributeKey.jobSavingURL] = outURL
        let op = web.printOperation(with: info)
        op.showsPrintPanel = false
        op.showsProgressPanel = false
        op.view?.frame = web.bounds
        op.runModal(for: window, delegate: self, didRun: #selector(done(_:success:contextInfo:)), contextInfo: nil)
    }

    @objc func done(_ op: NSPrintOperation, success: Bool, contextInfo: UnsafeMutableRawPointer?) {
        exit(success ? 0 : 1)
    }
}

let renderer = Renderer()
renderer.web.loadHTMLString(html, baseURL: nil)
DispatchQueue.main.asyncAfter(deadline: .now() + 30) { FileHandle.standardError.write("시간 초과\n".data(using: .utf8)!); exit(1) }
app.run()
