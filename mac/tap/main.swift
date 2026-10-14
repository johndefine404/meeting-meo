// [Define404]
// 미팅냥 소리 받기: 맥 시스템 소리(상대)와 마이크(나)를 16kHz 모노 16비트로 바꿔 표준출력에 프레임으로 내보낸다.
// 프레임 = 1바이트 출처(0 상대, 1 나) + 4바이트 길이(리틀엔디언) + PCM 바이트.
import AVFoundation
import CoreMedia
import Foundation
import ScreenCaptureKit

let outFormat = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16000, channels: 1, interleaved: true)!
let stdoutHandle = FileHandle.standardOutput
let writeLock = NSLock()

func log(_ s: String) {
    FileHandle.standardError.write((s + "\n").data(using: .utf8)!)
}

func emit(_ source: UInt8, _ data: Data) {
    var header = Data([source])
    var len = UInt32(data.count).littleEndian
    header.append(Data(bytes: &len, count: 4))
    writeLock.lock()
    stdoutHandle.write(header + data)
    writeLock.unlock()
}

final class Converter {
    var converter: AVAudioConverter?
    var inFormat: AVAudioFormat?

    func convert(_ buffer: AVAudioPCMBuffer) -> Data? {
        if inFormat == nil || inFormat! != buffer.format {
            inFormat = buffer.format
            converter = AVAudioConverter(from: buffer.format, to: outFormat)
        }
        guard let converter else { return nil }
        let ratio = outFormat.sampleRate / buffer.format.sampleRate
        let cap = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 32
        guard let out = AVAudioPCMBuffer(pcmFormat: outFormat, frameCapacity: cap) else { return nil }
        var fed = false
        var err: NSError?
        converter.convert(to: out, error: &err) { _, status in
            if fed { status.pointee = .noDataNow; return nil }
            fed = true
            status.pointee = .haveData
            return buffer
        }
        if err != nil || out.frameLength == 0 { return nil }
        return Data(bytes: out.int16ChannelData![0], count: Int(out.frameLength) * 2)
    }
}

func pcmBuffer(from sample: CMSampleBuffer) -> AVAudioPCMBuffer? {
    guard let desc = CMSampleBufferGetFormatDescription(sample),
          let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(desc) else { return nil }
    var streamDesc = asbd.pointee
    guard let format = AVAudioFormat(streamDescription: &streamDesc) else { return nil }
    let frames = AVAudioFrameCount(CMSampleBufferGetNumSamples(sample))
    guard let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frames) else { return nil }
    buffer.frameLength = frames
    let status = CMSampleBufferCopyPCMDataIntoAudioBufferList(
        sample, at: 0, frameCount: Int32(frames), into: buffer.mutableAudioBufferList)
    return status == noErr ? buffer : nil
}

final class Output: NSObject, SCStreamOutput, SCStreamDelegate {
    let them = Converter()
    let me = Converter()

    func stream(_ stream: SCStream, didOutputSampleBuffer sample: CMSampleBuffer, of type: SCStreamOutputType) {
        guard sample.isValid, let buf = pcmBuffer(from: sample) else { return }
        switch type {
        case .audio:
            if let d = them.convert(buf) { emit(0, d) }
        case .microphone:
            if let d = me.convert(buf) { emit(1, d) }
        default:
            break
        }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        log("stopped: \(error.localizedDescription)")
        exit(2)
    }
}

let output = Output()
var activeStream: SCStream?

Task {
    do {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
        guard let display = content.displays.first else { log("no display"); exit(1) }
        let filter = SCContentFilter(display: display, excludingWindows: [])
        let cfg = SCStreamConfiguration()
        cfg.capturesAudio = true
        cfg.excludesCurrentProcessAudio = true
        cfg.sampleRate = 48000
        cfg.channelCount = 1
        cfg.captureMicrophone = true
        cfg.width = 2
        cfg.height = 2
        cfg.minimumFrameInterval = CMTime(value: 1, timescale: 1)
        let stream = SCStream(filter: filter, configuration: cfg, delegate: output)
        let q = DispatchQueue(label: "audio")
        try stream.addStreamOutput(output, type: .audio, sampleHandlerQueue: q)
        try stream.addStreamOutput(output, type: .microphone, sampleHandlerQueue: q)
        try await stream.startCapture()
        activeStream = stream
        log("ready")
    } catch {
        log("error: \(error.localizedDescription)")
        exit(1)
    }
}

signal(SIGTERM) { _ in exit(0) }
signal(SIGINT) { _ in exit(0) }
RunLoop.main.run()
