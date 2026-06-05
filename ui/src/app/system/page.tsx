"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";

// ─── Types ────────────────────────────────────────────────────
interface StreamConfig {
    frame_skip_mode: "none" | "fixed" | "auto";
    frame_skip_n: number;
    target_fps: number;
    buffer_size: number;
    ai_frame_skip: number;
}

interface SystemConfig {
    detector_model: string;
    classifier_model: string;
    detection_confidence: number;
    iou_threshold: number;
    max_tracks: number;
    frame_skip: number;
    detection_enabled: boolean;
    classification_enabled: boolean;
    // nested sections (come from backend config as-is)
    processing?: { color_remove_background?: boolean };
    stream?: StreamConfig;
}

interface HardwareInfo {
    device: "cpu" | "cuda";
    device_name: string;
    gpu_count: number;
    cuda_available: boolean;
}

interface ModelFileInfo {
    path: string;
    exists: boolean;
    size_mb: number | null;
}

interface SettingsData {
    config: SystemConfig;
    defaults: SystemConfig;
    modified_keys: string[];
    hardware: HardwareInfo;
    models: {
        detector: ModelFileInfo;
        classifier: ModelFileInfo;
    };
}

interface ModelFile {
    name: string;
    path: string;
    size_mb: number;
}

type Tab = "MODELS" | "DETECTION" | "STREAM" | "SYSTEM" | "DATABASE" | "TEST";

const TAB_KEYS: Record<string, (keyof SystemConfig)[]> = {
    MODELS: ["detector_model", "classifier_model", "detection_enabled", "classification_enabled"],
    DETECTION: ["detection_confidence", "iou_threshold", "max_tracks", "frame_skip"],
};

// ─── Page ─────────────────────────────────────────────────────
export default function SystemPage() {
    const [activeTab, setActiveTab] = useState<Tab>("MODELS");
    const [data, setData] = useState<SettingsData | null>(null);
    const [modelFiles, setModelFiles] = useState<ModelFile[]>([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [resetting, setResetting] = useState(false);
    const [saveMsg, setSaveMsg] = useState<string | null>(null);
    const [draft, setDraft] = useState<Partial<SystemConfig>>({});
    const [modifiedKeys, setModifiedKeys] = useState<string[]>([]);
    const [uploadStatus, setUploadStatus] = useState<"idle" | "uploading" | "done" | "error">("idle");
    const [uploadMsg, setUploadMsg] = useState<string>("");
    const [isDragOver, setIsDragOver] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const fetchPromiseRef = useRef<Promise<void> | null>(null);
    const lastFetchAtRef = useRef(0);
    const backendUrl = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(
        "://localhost:",
        "://127.0.0.1:"
    );

    const fetchData = useCallback(async (force = false) => {
        const now = Date.now();
        if (!force && fetchPromiseRef.current) return fetchPromiseRef.current;
        if (!force && now - lastFetchAtRef.current < 2000) return;
        setLoading(true);
        const request = (async () => {
            const [settingsRes, modelsRes] = await Promise.all([
                fetch(`${backendUrl}/api/settings`, { cache: "no-store" }),
                fetch(`${backendUrl}/api/settings/models`, { cache: "no-store" }),
            ]);
            if (settingsRes.ok) {
                const d = await settingsRes.json();
                const normalized = {
                    ...d,
                    defaults: d.defaults ?? {},
                    modified_keys: Array.isArray(d.modified_keys) ? d.modified_keys : [],
                };
                setData(normalized);
                setDraft(d.config);
                setModifiedKeys(normalized.modified_keys);
            }
            if (modelsRes.ok) {
                const m = await modelsRes.json();
                setModelFiles(m.models ?? []);
            }
            lastFetchAtRef.current = Date.now();
        })();
        fetchPromiseRef.current = request;
        try {
            await request;
        } finally {
            fetchPromiseRef.current = null;
            setLoading(false);
        }
    }, [backendUrl]);

    useEffect(() => { fetchData(); }, [fetchData]);

    const handleSave = async () => {
        setSaving(true);
        setSaveMsg(null);
        try {
            const res = await fetch(`${backendUrl}/api/settings`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(draft),
            });
            if (res.ok) {
                setSaveMsg("✓ SAVED");
                await fetchData(true);
            } else {
                setSaveMsg("✗ FAILED");
            }
        } finally {
            setSaving(false);
            setTimeout(() => setSaveMsg(null), 2500);
        }
    };

    const handleReset = async (keys?: string[]) => {
        const msg = keys
            ? `Reset ${keys.length} setting(s) in this tab to factory defaults?`
            : "Restore ALL settings across all tabs to factory defaults?";
        if (!confirm(msg)) return;
        setResetting(true);
        setSaveMsg(null);
        try {
            const body = keys ? { keys } : {};
            const res = await fetch("/api/settings/reset", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            if (res.ok) {
                setSaveMsg(keys ? "✓ TAB RESET" : "✓ ALL RESET");
                await fetchData(true);
            } else {
                setSaveMsg("✗ RESET FAILED");
            }
        } finally {
            setResetting(false);
            setTimeout(() => setSaveMsg(null), 3000);
        }
    };

    const handleUpload = async (file: File) => {
        if (!file.name.endsWith(".pt")) {
            setUploadMsg("Only .pt files accepted");
            setUploadStatus("error");
            return;
        }
        setUploadStatus("uploading");
        setUploadMsg(`Uploading ${file.name}…`);
        const form = new FormData();
        form.append("file", file);
        try {
            const res = await fetch(`${backendUrl}/api/settings/models/upload`, { method: "POST", body: form });
            const json = await res.json();
            if (res.ok) {
                setUploadStatus("done");
                setUploadMsg(`✓ ${json.name} uploaded (${json.size_mb} MB)`);
                await fetchData(true);
            } else {
                setUploadStatus("error");
                setUploadMsg(json.error ?? "Upload failed");
            }
        } catch {
            setUploadStatus("error");
            setUploadMsg("Network error");
        }
    };

    const tabs: Tab[] = ["MODELS", "DETECTION", "STREAM", "SYSTEM", "DATABASE", "TEST"];

    return (
        <div className="flex flex-col h-screen bg-slate-950 text-slate-300 overflow-hidden">
            {/* ── Header ── */}
            <header className="flex-shrink-0 border-b border-slate-800/60 px-6 py-4">
                <div className="flex items-center gap-4">
                    <div className="w-9 h-9 border border-orange-500/60 flex items-center justify-center bg-orange-950/30">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5 text-orange-400">
                            <path d="M12 15a3 3 0 100-6 3 3 0 000 6z" />
                            <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
                        </svg>
                    </div>
                    <div>
                        <h1 className="font-orbitron text-base font-bold text-orange-400 tracking-[0.2em]">SYSTEM SETTINGS</h1>
                        <p className="font-mono text-xs text-slate-500 tracking-widest">AI ENGINE CONFIGURATION</p>
                    </div>
                    {/* Tab bar */}
                    <div className="ml-8 flex gap-1">
                        {tabs.map((t) => (
                            <button
                                key={t}
                                onClick={() => setActiveTab(t)}
                                className={`px-5 py-2 font-mono text-xs tracking-[0.15em] rounded-sm border transition-all ${activeTab === t
                                    ? "border-orange-500/60 bg-orange-950/30 text-orange-400"
                                    : "border-slate-800 text-slate-500 hover:text-slate-300 hover:border-slate-700"
                                    }`}
                            >
                                {t}
                            </button>
                        ))}
                    </div>
                    {/* Right controls */}
                    <div className="ml-auto flex items-center gap-3">
                        {saveMsg && (
                            <span className={`font-mono text-xs ${saveMsg.startsWith("✓") ? "text-green-400" : "text-red-400"}`}>
                                {saveMsg}
                            </span>
                        )}
                        {modifiedKeys.length > 0 && (
                            <span className="font-mono text-xs text-amber-400/80 border border-amber-700/40 bg-amber-950/20 px-3 py-1 rounded-sm">
                                {modifiedKeys.length} MODIFIED
                            </span>
                        )}
                        <button
                            onClick={() => handleReset()}
                            disabled={resetting}
                            title="Restore ALL settings across all tabs to factory defaults"
                            className="font-mono text-xs font-bold px-4 py-2 rounded-sm border border-slate-600/60 bg-slate-900/40 text-slate-400
                hover:bg-slate-800/60 hover:border-red-500/40 hover:text-red-300 transition-all disabled:opacity-30 tracking-widest"
                        >
                            {resetting ? "RESTORING…" : "↺ RESET ALL"}
                        </button>
                        <button
                            onClick={handleSave}
                            disabled={saving}
                            className="font-mono text-xs font-bold px-5 py-2 rounded-sm border border-orange-500/60 bg-orange-950/30 text-orange-400
                hover:bg-orange-900/40 hover:border-orange-400 transition-all disabled:opacity-50 tracking-widest"
                        >
                            {saving ? "SAVING…" : "SAVE CONFIG"}
                        </button>
                    </div>
                </div>
            </header>

            {/* ── Body ── */}
            <div className="flex-1 overflow-y-auto p-6">
                {loading ? (
                    <div className="flex items-center justify-center h-48 gap-3">
                        <div className="w-5 h-5 border-2 border-orange-500/40 border-t-orange-400 rounded-full animate-spin" />
                        <span className="font-mono text-sm text-slate-500 tracking-widest">LOADING SYSTEM CONFIG…</span>
                    </div>
                ) : (
                    <>
                        {activeTab === "MODELS" && (
                            <ModelsTab
                                data={data}
                                draft={draft}
                                setDraft={setDraft}
                                modelFiles={modelFiles}
                                modifiedKeys={modifiedKeys}
                                uploadStatus={uploadStatus}
                                uploadMsg={uploadMsg}
                                isDragOver={isDragOver}
                                setIsDragOver={setIsDragOver}
                                fileInputRef={fileInputRef}
                                onUpload={handleUpload}
                                onResetTab={() => handleReset(TAB_KEYS.MODELS as string[])}
                                resetting={resetting}
                            />
                        )}
                        {activeTab === "DETECTION" && (
                            <DetectionTab
                                draft={draft}
                                setDraft={setDraft}
                                defaults={data?.defaults}
                                modifiedKeys={modifiedKeys}
                                onResetTab={() => handleReset(TAB_KEYS.DETECTION as string[])}
                                resetting={resetting}
                            />
                        )}
                        {activeTab === "STREAM" && <StreamTab draft={draft} setDraft={setDraft} />}
                        {activeTab === "SYSTEM" && <SystemTab data={data} draft={draft} setDraft={setDraft} />}
                        {activeTab === "DATABASE" && <DatabaseTab />}
                        {activeTab === "TEST" && <TestTab backendUrl={backendUrl} />}
                    </>
                )}
            </div>
        </div>
    );
}

// ─── Tab: Models ──────────────────────────────────────────────
function ModelsTab({
    data, draft, setDraft, modelFiles, modifiedKeys,
    uploadStatus, uploadMsg, isDragOver, setIsDragOver, fileInputRef, onUpload,
    onResetTab, resetting,
}: {
    data: SettingsData | null;
    draft: Partial<SystemConfig>;
    setDraft: React.Dispatch<React.SetStateAction<Partial<SystemConfig>>>;
    modelFiles: ModelFile[];
    modifiedKeys: string[];
    uploadStatus: string;
    uploadMsg: string;
    isDragOver: boolean;
    setIsDragOver: (v: boolean) => void;
    fileInputRef: React.RefObject<HTMLInputElement | null>;
    onUpload: (f: File) => void;
    onResetTab: () => void;
    resetting: boolean;
}) {
    return (
        <>
            <div className="grid grid-cols-2 gap-6 w-full">
                {/* Detector */}
                <SettingsCard title="PERSON DETECTOR" modified={modifiedKeys.includes("detector_model")}>
                    <FieldLabel>Model File</FieldLabel>
                    <select
                        value={draft.detector_model ?? ""}
                        onChange={(e) => setDraft((d) => ({ ...d, detector_model: e.target.value }))}
                        className="w-full bg-slate-900/60 border border-slate-700/60 rounded-sm px-3 py-2.5 font-mono text-sm text-slate-300 outline-none focus:border-orange-500/60 appearance-none"
                    >
                        {modelFiles.map((m) => (
                            <option key={m.path} value={m.path}>{m.name} ({m.size_mb} MB)</option>
                        ))}
                        {modelFiles.length === 0 && <option value="">No models found</option>}
                    </select>
                    <StatusBadge exists={data?.models.detector.exists ?? false} size={data?.models.detector.size_mb} />
                    {data?.defaults?.detector_model && draft.detector_model !== data.defaults.detector_model && (
                        <DefaultHint value={data.defaults.detector_model} />
                    )}
                    <div className="mt-4">
                        <Toggle
                            label="DETECTION ENABLED"
                            value={draft.detection_enabled ?? true}
                            onChange={(v) => setDraft((d) => ({ ...d, detection_enabled: v }))}
                        />
                    </div>
                </SettingsCard>

                {/* Classifier */}
                <SettingsCard title="CLOTHING CLASSIFIER" modified={modifiedKeys.includes("classifier_model")}>
                    <FieldLabel>Model File</FieldLabel>
                    <select
                        value={draft.classifier_model ?? ""}
                        onChange={(e) => setDraft((d) => ({ ...d, classifier_model: e.target.value }))}
                        className="w-full bg-slate-900/60 border border-slate-700/60 rounded-sm px-3 py-2.5 font-mono text-sm text-slate-300 outline-none focus:border-orange-500/60 appearance-none"
                    >
                        {modelFiles.map((m) => (
                            <option key={m.path} value={m.path}>{m.name} ({m.size_mb} MB)</option>
                        ))}
                        {modelFiles.length === 0 && <option value="">No models found</option>}
                    </select>
                    <StatusBadge exists={data?.models.classifier.exists ?? false} size={data?.models.classifier.size_mb} />
                    {data?.defaults?.classifier_model && draft.classifier_model !== data.defaults.classifier_model && (
                        <DefaultHint value={data.defaults.classifier_model} />
                    )}
                    <div className="mt-4">
                        <Toggle
                            label="CLASSIFICATION ENABLED"
                            value={draft.classification_enabled ?? true}
                            onChange={(v) => setDraft((d) => ({ ...d, classification_enabled: v }))}
                        />
                    </div>
                </SettingsCard>

                {/* Upload Zone */}
                <div className="col-span-2">
                    <SettingsCard title="IMPORT MODEL">
                        <div
                            className={`relative border-2 border-dashed rounded-sm p-12 flex flex-col items-center justify-center gap-4 cursor-pointer transition-all duration-200
                ${isDragOver ? "border-orange-400 bg-orange-950/20"
                                    : uploadStatus === "done" ? "border-green-500/50 bg-green-950/10"
                                        : uploadStatus === "error" ? "border-red-500/50 bg-red-950/10"
                                            : "border-slate-700 hover:border-slate-600 bg-slate-900/20"}`}
                            onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
                            onDragLeave={() => setIsDragOver(false)}
                            onDrop={(e) => { e.preventDefault(); setIsDragOver(false); const f = e.dataTransfer.files[0]; if (f) onUpload(f); }}
                            onClick={() => fileInputRef.current?.click()}
                        >
                            <input ref={fileInputRef} type="file" accept=".pt" className="hidden"
                                onChange={(e) => { const f = e.target.files?.[0]; if (f) onUpload(f); e.target.value = ""; }} />
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}
                                className={`w-10 h-10 ${isDragOver ? "text-orange-400" : "text-slate-600"}`}>
                                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" />
                            </svg>
                            {uploadStatus === "uploading" ? (
                                <div className="flex items-center gap-2">
                                    <div className="w-4 h-4 border border-orange-400/40 border-t-orange-400 rounded-full animate-spin" />
                                    <span className="font-mono text-sm text-orange-400">{uploadMsg}</span>
                                </div>
                            ) : (
                                <span className={`font-mono text-sm text-center ${uploadStatus === "done" ? "text-green-400" : uploadStatus === "error" ? "text-red-400" : "text-slate-500"}`}>
                                    {uploadMsg || "DROP .pt MODEL FILE HERE OR CLICK TO BROWSE"}
                                </span>
                            )}
                            <span className="font-mono text-xs text-slate-600">Supported: YOLOv8 / v9 / v10 .pt format</span>
                        </div>
                    </SettingsCard>
                </div>
            </div>
            <ResetTabBar label="MODELS TAB" onReset={onResetTab} resetting={resetting} />
        </>
    );
}

// ─── Tab: Detection Config ─────────────────────────────────────
function DetectionTab({
    draft, setDraft, defaults, modifiedKeys, onResetTab, resetting,
}: {
    draft: Partial<SystemConfig>;
    setDraft: React.Dispatch<React.SetStateAction<Partial<SystemConfig>>>;
    defaults?: SystemConfig;
    modifiedKeys: string[];
    onResetTab: () => void;
    resetting: boolean;
}) {
    return (
        <>
            <div className="grid grid-cols-2 gap-6 w-full">
                <SettingsCard title="DETECTION THRESHOLDS" modified={modifiedKeys.includes("detection_confidence") || modifiedKeys.includes("iou_threshold")}>
                    <SliderField
                        label="CONFIDENCE THRESHOLD"
                        description="Minimum confidence to accept a detection"
                        value={draft.detection_confidence ?? 0.5}
                        min={0.1} max={1.0} step={0.05}
                        display={(v) => `${Math.round(v * 100)}%`}
                        onChange={(v) => setDraft((d) => ({ ...d, detection_confidence: v }))}
                        defaultValue={defaults?.detection_confidence}
                        modified={modifiedKeys.includes("detection_confidence")}
                    />
                    <div className="mt-6">
                        <SliderField
                            label="IOU THRESHOLD"
                            description="Non-maximum suppression overlap threshold"
                            value={draft.iou_threshold ?? 0.45}
                            min={0.1} max={0.95} step={0.05}
                            display={(v) => `${Math.round(v * 100)}%`}
                            onChange={(v) => setDraft((d) => ({ ...d, iou_threshold: v }))}
                            defaultValue={defaults?.iou_threshold}
                            modified={modifiedKeys.includes("iou_threshold")}
                        />
                    </div>
                </SettingsCard>

                <SettingsCard title="TRACKING PARAMETERS" modified={modifiedKeys.includes("max_tracks") || modifiedKeys.includes("frame_skip")}>
                    <SliderField
                        label="MAX CONCURRENT TRACKS"
                        description="Maximum number of persons tracked simultaneously"
                        value={draft.max_tracks ?? 50}
                        min={5} max={200} step={5}
                        display={(v) => String(v)}
                        onChange={(v) => setDraft((d) => ({ ...d, max_tracks: v }))}
                        defaultValue={defaults?.max_tracks}
                        modified={modifiedKeys.includes("max_tracks")}
                    />
                    <div className="mt-6">
                        <SliderField
                            label="FRAME SKIP"
                            description="Process every Nth frame (1 = all frames)"
                            value={draft.frame_skip ?? 2}
                            min={1} max={10} step={1}
                            display={(v) => `${v}x`}
                            onChange={(v) => setDraft((d) => ({ ...d, frame_skip: v }))}
                            defaultValue={defaults?.frame_skip}
                            modified={modifiedKeys.includes("frame_skip")}
                        />
                    </div>
                </SettingsCard>
            </div>
            <ResetTabBar label="DETECTION TAB" onReset={onResetTab} resetting={resetting} />
        </>
    );
}

// ─── Tab: Stream Config ───────────────────────────────────────
function StreamTab({
    draft,
    setDraft,
}: {
    draft: Partial<SystemConfig>;
    setDraft: React.Dispatch<React.SetStateAction<Partial<SystemConfig>>>;
}) {
    const stream: StreamConfig = {
        frame_skip_mode: "auto",
        frame_skip_n: 2,
        target_fps: 15,
        buffer_size: 1,
        ai_frame_skip: 5,
        ...(draft.stream ?? {}),
    };

    const set = (patch: Partial<StreamConfig>) =>
        setDraft((d) => ({ ...d, stream: { ...stream, ...patch } }));

    const mode = stream.frame_skip_mode;

    return (
        <div className="grid grid-cols-2 gap-6 w-full">
            {/* Frame Skip Mode */}
            <SettingsCard title="FRAME SKIP MODE">
                <p className="font-mono text-[10px] text-slate-500 leading-relaxed mb-4">
                    ควบคุมว่า backend จะประมวลผล frame ไหนก่อนส่งมาแสดง<br />
                    มีผลเฉพาะ live stream ที่ยังไม่ได้กด START AI
                </p>
                <div className="flex flex-col gap-3">
                    {(["none", "fixed", "auto"] as const).map((m) => (
                        <ModeCard
                            key={m}
                            active={mode === m}
                            onClick={() => set({ frame_skip_mode: m })}
                            label={m === "none" ? "NONE — ไม่ skip" : m === "fixed" ? "FIXED — skip ตายตัว" : "AUTO — skip อัตโนมัติ"}
                            badge={m === "auto" ? "แนะนำ" : undefined}
                            description={
                                m === "none"
                                    ? "ส่งทุก frame เรียงลำดับ ไม่ข้ามเลย ได้ภาพลื่นสุด แต่ delay จะเพิ่มถ้า decode ไม่ทันกับ FPS ต้นทาง"
                                    : m === "fixed"
                                    ? `เอา 1 ใน ${stream.frame_skip_n} frame เสมอ เช่น N=2 คือเอา frame 1, 3, 5... frame คู่ถูกข้ามทิ้ง ใช้เมื่อรู้ว่า hardware ทำได้แค่ไหน`
                                    : "วัดความเร็ว decode จริงแล้วล้าง buffer ทิ้งก่อนอ่าน frame ใหม่เสมอ ได้ frame ปัจจุบันที่สุด delay ต่ำสุด แต่ภาพอาจกระตุกเล็กน้อย"
                            }
                        />
                    ))}
                </div>
            </SettingsCard>

            {/* Parameters */}
            <div className="flex flex-col gap-6">
                {/* Fixed N — แสดงเฉพาะ fixed mode */}
                <SettingsCard title="FIXED SKIP — N (frame)">
                    <div className={`transition-opacity ${mode === "fixed" ? "opacity-100" : "opacity-30 pointer-events-none"}`}>
                        <SliderField
                            label="SKIP EVERY N FRAMES"
                            description={`เอา 1 ใน ${stream.frame_skip_n} frame | ใช้ได้เฉพาะ mode = FIXED`}
                            value={stream.frame_skip_n}
                            min={1} max={10} step={1}
                            display={(v) => `N = ${v}`}
                            onChange={(v) => set({ frame_skip_n: v })}
                        />
                        <InfoBox color="blue">
                            N=1 คือเอาทุก frame (= none), N=3 คือเอา frame ที่ 1, 4, 7, 10...
                            ยิ่ง N มาก ยิ่ง CPU ต่ำ แต่ภาพกระตุกมากขึ้น
                        </InfoBox>
                    </div>
                    {mode !== "fixed" && (
                        <p className="font-mono text-[10px] text-slate-600">เปิดใช้เมื่อเลือก mode = FIXED</p>
                    )}
                </SettingsCard>

                {/* Target FPS — แสดงเฉพาะ auto mode */}
                <SettingsCard title="AUTO TARGET FPS">
                    <div className={`transition-opacity ${mode === "auto" ? "opacity-100" : "opacity-30 pointer-events-none"}`}>
                        <SliderField
                            label="TARGET OUTPUT FPS"
                            description={`ส่งภาพไปหน้าบ้านที่ ~${stream.target_fps} fps | ใช้ได้เฉพาะ mode = AUTO`}
                            value={stream.target_fps}
                            min={1} max={30} step={1}
                            display={(v) => `${v} fps`}
                            onChange={(v) => set({ target_fps: v })}
                        />
                        <InfoBox color="green">
                            ระบบจะล้าง queue ก่อนอ่าน frame ใหม่เสมอ แล้ว rate-limit ที่ค่านี้
                            ค่าแนะนำ 15 fps — สมดุลระหว่าง latency และ CPU load
                        </InfoBox>
                    </div>
                    {mode !== "auto" && (
                        <p className="font-mono text-[10px] text-slate-600">เปิดใช้เมื่อเลือก mode = AUTO</p>
                    )}
                </SettingsCard>

                {/* Buffer Size */}
                <SettingsCard title="OPENCV BUFFER SIZE">
                    <SliderField
                        label="CAP_PROP_BUFFERSIZE"
                        description="จำนวน frame ที่ OpenCV เก็บไว้รอใน internal queue"
                        value={stream.buffer_size}
                        min={1} max={10} step={1}
                        display={(v) => `${v} frame`}
                        onChange={(v) => set({ buffer_size: v })}
                    />
                    <InfoBox color="amber">
                        ค่า 1 = buffer น้อยสุด delay ต่ำสุด แต่อาจ drop frame ถ้า network ไม่เสถียร
                        ค่า 4-10 = smooth กว่า แต่ delay เพิ่ม ~100-300ms
                    </InfoBox>
                </SettingsCard>

                {/* AI Frame Skip */}
                <SettingsCard title="AI PROCESSING — FRAME SKIP">
                    <SliderField
                        label="AI FRAME SKIP"
                        description="ประมวลผล AI ทุก N frame (ใช้กับ START NEW บน dashboard)"
                        value={stream.ai_frame_skip}
                        min={1} max={30} step={1}
                        display={(v) => `N = ${v}`}
                        onChange={(v) => set({ ai_frame_skip: v })}
                    />
                    <InfoBox color="blue">
                        N=1 = ทุก frame (หนัก), N=5 = ~6fps จาก 30fps (แนะนำ), N=10 = ~3fps (เบา)
                        ยิ่ง N น้อย ยิ่ง detect ถี่ แต่ใช้ GPU/CPU มากขึ้น
                    </InfoBox>
                </SettingsCard>
            </div>

            {/* Summary */}
            <div className="col-span-2">
                <SettingsCard title="CURRENT CONFIG SUMMARY">
                    <div className="grid grid-cols-5 gap-4">
                        <SummaryCell label="MODE" value={mode.toUpperCase()} color="text-cyan-400" />
                        <SummaryCell
                            label={mode === "fixed" ? "SKIP N" : "TARGET FPS"}
                            value={mode === "fixed" ? `N = ${stream.frame_skip_n}` : mode === "auto" ? `${stream.target_fps} fps` : "—"}
                            color="text-orange-400"
                        />
                        <SummaryCell label="BUFFER" value={`${stream.buffer_size} frame`} color="text-slate-300" />
                        <SummaryCell label="AI SKIP" value={`N = ${stream.ai_frame_skip}`} color="text-purple-400" />
                        <SummaryCell
                            label="EST. LATENCY"
                            value={
                                mode === "none"
                                    ? "สูง (ตาม queue)"
                                    : mode === "fixed"
                                    ? `~${Math.round((stream.frame_skip_n / 30) * 1000)}ms`
                                    : `~${Math.round(1000 / stream.target_fps)}ms`
                            }
                            color="text-green-400"
                        />
                    </div>
                </SettingsCard>
            </div>
        </div>
    );
}

function ModeCard({
    active, onClick, label, badge, description,
}: {
    active: boolean; onClick: () => void; label: string; badge?: string; description: string;
}) {
    const [open, setOpen] = React.useState(false);
    return (
        <div
            onClick={onClick}
            className={`border rounded-sm p-3 cursor-pointer transition-all ${
                active
                    ? "border-cyan-500/60 bg-cyan-950/20"
                    : "border-slate-700 bg-slate-900/30 hover:border-slate-600"
            }`}
        >
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className={`w-3 h-3 rounded-full border-2 flex-shrink-0 transition-all ${
                        active ? "border-cyan-400 bg-cyan-400" : "border-slate-600"
                    }`} />
                    <span className={`font-mono text-xs font-bold tracking-widest ${active ? "text-cyan-300" : "text-slate-400"}`}>
                        {label}
                    </span>
                    {badge && (
                        <span className="font-mono text-[9px] px-1.5 py-0.5 rounded-sm bg-green-900/40 border border-green-700/40 text-green-400">
                            {badge}
                        </span>
                    )}
                </div>
                <button
                    onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
                    className="font-mono text-[9px] text-slate-600 hover:text-slate-400 border border-slate-700 hover:border-slate-600 px-2 py-0.5 rounded-sm transition-all"
                >
                    {open ? "ซ่อน ▲" : "คำอธิบาย ▼"}
                </button>
            </div>
            {open && (
                <p className="font-mono text-[10px] text-slate-400 leading-relaxed mt-2 pl-6 border-l border-slate-700">
                    {description}
                </p>
            )}
        </div>
    );
}

function InfoBox({ color, children }: { color: "blue" | "green" | "amber"; children: React.ReactNode }) {
    const styles = {
        blue: "border-blue-800/40 bg-blue-950/20 text-blue-300",
        green: "border-green-800/40 bg-green-950/20 text-green-300",
        amber: "border-amber-700/40 bg-amber-950/20 text-amber-300",
    };
    return (
        <p className={`font-mono text-[10px] leading-relaxed border rounded-sm px-3 py-2 mt-3 ${styles[color]}`}>
            {children}
        </p>
    );
}

function SummaryCell({ label, value, color }: { label: string; value: string; color: string }) {
    return (
        <div className="border border-slate-800 bg-slate-900/40 rounded-sm p-3 text-center">
            <p className="font-mono text-[9px] text-slate-600 tracking-widest mb-1">{label}</p>
            <p className={`font-mono text-sm font-bold ${color}`}>{value}</p>
        </div>
    );
}

// ─── Tab: System Info ─────────────────────────────────────────
function SystemTab({
    data,
    draft,
    setDraft,
}: {
    data: SettingsData | null;
    draft: Partial<SystemConfig>;
    setDraft: React.Dispatch<React.SetStateAction<Partial<SystemConfig>>>;
}) {
    if (!data) return null;
    const hw = data.hardware;
    const modifiedKeys = Array.isArray(data.modified_keys) ? data.modified_keys : [];
    const defaults = data.defaults ?? {};
    const removeBg = draft.processing?.color_remove_background ?? true;
    return (
        <div className="grid grid-cols-3 gap-6 w-full">
            <SettingsCard title="PROCESSING SETTINGS">
                <FieldLabel>COLOR ANALYSIS</FieldLabel>
                <div className="space-y-4">
                    <div className="flex items-start justify-between gap-4">
                        <div>
                            <p className="font-mono text-xs text-slate-300">Background Removal</p>
                            <p className="font-mono text-[10px] text-slate-500 mt-1 leading-relaxed">
                                ตัด BG ก่อนนับสีเสื้อผ้า (rembg / GrabCut)<br />
                                ปิดเพื่อความเร็ว แต่สีอาจ mix กับฉากหลัง
                            </p>
                        </div>
                        <Toggle
                            label="REMOVE BG"
                            value={removeBg}
                            onChange={(v) =>
                                setDraft((d) => ({
                                    ...d,
                                    processing: { ...d.processing, color_remove_background: v },
                                }))
                            }
                        />
                    </div>
                    <div className={`px-3 py-2 rounded-sm border font-mono text-[10px] leading-relaxed ${
                        removeBg
                            ? "border-green-800/40 bg-green-950/20 text-green-400"
                            : "border-amber-700/40 bg-amber-950/20 text-amber-400"
                    }`}>
                        {removeBg
                            ? "✓ BG removal ON — สีแม่นขึ้น (~10–50ms/item)"
                            : "⚡ BG removal OFF — เร็วกว่า แต่สี BG อาจปน"}
                    </div>
                </div>
            </SettingsCard>

            <SettingsCard title="HARDWARE">
                <InfoRow label="DEVICE" value={hw.device.toUpperCase()} highlight={hw.device === "cuda"} />
                <InfoRow label="GPU NAME" value={hw.device_name} />
                <InfoRow label="GPU COUNT" value={String(hw.gpu_count)} />
                <InfoRow label="CUDA" value={hw.cuda_available ? "AVAILABLE" : "NOT AVAILABLE"} highlight={hw.cuda_available} />
            </SettingsCard>

            <SettingsCard title="MODEL STATUS">
                <FieldLabel>DETECTOR</FieldLabel>
                <span className="font-mono text-xs text-slate-400 break-all">{data.models.detector.path}</span>
                <StatusBadge exists={data.models.detector.exists} size={data.models.detector.size_mb} />
                <div className="mt-4">
                    <FieldLabel>CLASSIFIER</FieldLabel>
                    <span className="font-mono text-xs text-slate-400 break-all">{data.models.classifier.path}</span>
                    <StatusBadge exists={data.models.classifier.exists} size={data.models.classifier.size_mb} />
                </div>
            </SettingsCard>

            <SettingsCard title="SYSTEM INFO">
                <InfoRow label="VERSION" value="v2.4.1" />
                <InfoRow label="API FRAMEWORK" value="FastAPI" />
                <InfoRow label="AI FRAMEWORK" value="Ultralytics YOLO" />
                <InfoRow label="FRONTEND" value="Next.js 14" />
                <InfoRow label="STORE" value="PostgreSQL + MinIO" />
            </SettingsCard>

            <div className="col-span-3">
                <SettingsCard title="ACTIVE CONFIGURATION">
                    <div className="grid grid-cols-3 gap-4">
                        {Object.entries(data.config).map(([k, v]) => {
                            const isModified = modifiedKeys.includes(k);
                            const defaultVal = defaults[k as keyof SystemConfig];
                            return (
                                <div key={k} className={`border rounded-sm p-4 ${isModified ? "bg-amber-950/20 border-amber-700/40" : "bg-slate-900/40 border-slate-800"}`}>
                                    <div className={`font-mono text-xs tracking-widest uppercase mb-1 flex items-center gap-1 ${isModified ? "text-amber-600" : "text-slate-500"}`}>
                                        {k.replaceAll("_", " ")}
                                        {isModified && <span className="text-amber-400">✎</span>}
                                    </div>
                                    <div className={`font-mono text-base font-bold ${isModified ? "text-amber-400" : "text-orange-400"}`}>{String(v)}</div>
                                    {isModified && defaultVal !== undefined && (
                                        <div className="font-mono text-xs text-slate-500 mt-1">default: {String(defaultVal)}</div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </SettingsCard>
            </div>
        </div>
    );
}

// ─── Tab: Database ────────────────────────────────────────────
interface CameraJobInfo {
    camera_id: string;
    stream_jobs: number;
    video_jobs: number;
    total_jobs: number;
}

function DatabaseTab() {
    const [stats, setStats] = useState<{ detections: number; videos: number; cameras: number; store: "db" | "json" } | null>(null);
    const [purging, setPurging] = useState(false);
    const [purgeMsg, setPurgeMsg] = useState<string | null>(null);
    const [cameraJobs, setCameraJobs] = useState<CameraJobInfo[]>([]);
    const [selectedCam, setSelectedCam] = useState<string>("");
    const [deleteType, setDeleteType] = useState<"all" | "stream" | "non_stream">("all");
    const [deleting, setDeleting] = useState(false);
    const [deleteMsg, setDeleteMsg] = useState<string | null>(null);
    const backendUrl = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(
        "://localhost:",
        "://127.0.0.1:"
    );

    const loadCameraJobs = React.useCallback(async () => {
        const res = await fetch(`${backendUrl}/api/json/cameras`).then((r) => r.json()).catch(() => null);
        if (res?.cameras) {
            setCameraJobs(res.cameras);
            if (res.cameras.length > 0 && !selectedCam) setSelectedCam(res.cameras[0].camera_id);
        }
    }, [backendUrl, selectedCam]);

    useEffect(() => {
        let cancelled = false;

        const loadStats = async () => {
            const status = await fetch(`${backendUrl}/api/json/status`).then((r) => r.json()).catch(() => null);
            if (cancelled) return;

            if (status?.storage_mode === "json") {
                const jsonStats = await fetch(`${backendUrl}/api/json/stats`).then((r) => r.json()).catch(() => null);
                if (!cancelled) {
                    setStats({
                        detections: Number(jsonStats?.detections ?? 0),
                        videos: Number(jsonStats?.jobs ?? 0),
                        cameras: Number(jsonStats?.cameras ?? 0),
                        store: "json",
                    });
                }
                return;
            }

            const [det, vids, cams] = await Promise.all([
                fetch("/api/video/detections?limit=1").then((r) => r.json()).catch(() => null),
                fetch("/api/video/videos").then((r) => r.json()).catch(() => null),
                fetch(`${backendUrl}/api/cameras`).then((r) => r.json()).catch(() => null),
            ]);
            if (!cancelled) {
                setStats({
                    detections: Array.isArray(det) ? det.length : 0,
                    videos: Array.isArray(vids) ? vids.length : 0,
                    cameras: Array.isArray(cams?.cameras) ? cams.cameras.length : 0,
                    store: "db",
                });
            }
        };

        void loadStats();
        return () => {
            cancelled = true;
        };
    }, [backendUrl]);

    useEffect(() => { void loadCameraJobs(); }, [backendUrl]);

    return (
        <div className="grid grid-cols-2 gap-6 w-full">
            <SettingsCard title="CONNECTION">
                <InfoRow label="STORE MODE" value={stats?.store === "json" ? "JSON FILES" : "DATABASE"} highlight={stats?.store === "json"} />
                <InfoRow label="HOST" value={stats?.store === "json" ? "LOCAL FILESYSTEM" : "localhost:5432"} />
                <InfoRow label="DATABASE" value={stats?.store === "json" ? "DISABLED" : "cctv_analytics"} />
                <InfoRow label="OBJECT STORE" value={stats?.store === "json" ? "DISABLED" : "MinIO"} />
            </SettingsCard>

            <SettingsCard title="DATA SUMMARY">
                <InfoRow label="DETECTIONS" value={stats ? String(stats.detections) : "..."} />
                <InfoRow label={stats?.store === "json" ? "JSON JOBS" : "VIDEOS"} value={stats ? String(stats.videos) : "..."} />
                <InfoRow label="CAMERAS" value={stats ? String(stats.cameras) : "…"} />
            </SettingsCard>

            <div className="col-span-2">
                <SettingsCard title="MAINTENANCE">
                    <div className="flex gap-6 items-center">
                        <div className="flex-1">
                            <FieldLabel>PURGE DETECTIONS</FieldLabel>
                            <p className="font-mono text-sm text-slate-500 mt-1">
                                {stats?.store === "json"
                                    ? "Delete JSON result folders, job index records, queue state, and local saved images. This cannot be undone."
                                    : "Delete all detection records from the database. This cannot be undone."}
                            </p>
                        </div>
                        <button
                            onClick={async () => {
                                const message = stats?.store === "json"
                                    ? "Delete ALL JSON mode results and local saved images under the configured JSON result root? This cannot be undone."
                                    : "Delete ALL detection records? This cannot be undone.";
                                if (!confirm(message)) return;
                                setPurging(true);
                                setPurgeMsg(null);
                                try {
                                    const response = stats?.store === "json"
                                        ? await fetch(`${backendUrl}/api/json/clear`, { method: "DELETE" })
                                        : await fetch(`${backendUrl}/api/video/clear?type=all&delete_img=true`, { method: "DELETE" });
                                    const data = await response.json().catch(() => ({}));
                                    if (!response.ok) throw new Error(data.detail || data.error || "Purge failed");
                                    setPurgeMsg(stats?.store === "json"
                                        ? `JSON cleared: ${data.deleted_dirs ?? 0} result folders removed`
                                        : "Database records cleared");
                                    setStats((prev) => prev ? { ...prev, detections: 0, videos: 0 } : prev);
                                } catch (error) {
                                    setPurgeMsg(error instanceof Error ? error.message : "Purge failed");
                                } finally {
                                    setPurging(false);
                                    setTimeout(() => setPurgeMsg(null), 5000);
                                }
                            }}
                            disabled={purging}
                            className="flex-shrink-0 font-mono text-sm font-bold px-6 py-2.5 rounded-sm border border-red-500/60 bg-red-950/30 text-red-400 hover:bg-red-900/40 hover:border-red-400 transition-all disabled:opacity-50"
                        >
                            {purging ? "PURGING…" : "PURGE ALL"}
                        </button>
                    </div>
                    {purgeMsg && <p className="font-mono text-sm text-yellow-400 mt-3">{purgeMsg}</p>}
                </SettingsCard>
            </div>

            {/* Camera Data Management */}
            <div className="col-span-2">
                <SettingsCard title="CAMERA DATA MANAGEMENT">
                    {cameraJobs.length === 0 ? (
                        <p className="font-mono text-xs text-slate-600">ไม่พบข้อมูล job ในระบบ</p>
                    ) : (
                        <div className="flex flex-col gap-4">
                            {/* Camera selector */}
                            <div className="grid grid-cols-3 gap-4">
                                {cameraJobs.map((cam) => (
                                    <button
                                        key={cam.camera_id}
                                        onClick={() => setSelectedCam(cam.camera_id)}
                                        className={`border rounded-sm p-3 text-left transition-all ${
                                            selectedCam === cam.camera_id
                                                ? "border-cyan-500/60 bg-cyan-950/20"
                                                : "border-slate-700 bg-slate-900/30 hover:border-slate-600"
                                        }`}
                                    >
                                        <p className={`font-mono text-xs font-bold tracking-widest mb-2 ${selectedCam === cam.camera_id ? "text-cyan-300" : "text-slate-400"}`}>
                                            {cam.camera_id}
                                        </p>
                                        <div className="flex gap-3">
                                            <span className="font-mono text-[9px] text-blue-400">LIVE {cam.stream_jobs}</span>
                                            <span className="font-mono text-[9px] text-orange-400">VIDEO {cam.video_jobs}</span>
                                            <span className="font-mono text-[9px] text-slate-500">TOTAL {cam.total_jobs}</span>
                                        </div>
                                    </button>
                                ))}
                            </div>

                            {/* Delete type */}
                            {selectedCam && (
                                <div className="flex flex-col gap-3 border-t border-slate-800/60 pt-4">
                                    <FieldLabel>ลบข้อมูลของกล้อง: <span className="text-cyan-400">{selectedCam}</span></FieldLabel>
                                    <div className="flex gap-2">
                                        {(["all", "stream", "non_stream"] as const).map((t) => (
                                            <button
                                                key={t}
                                                onClick={() => setDeleteType(t)}
                                                className={`px-3 py-1.5 font-mono text-xs rounded-sm border transition-all ${
                                                    deleteType === t
                                                        ? "border-red-500/60 bg-red-950/20 text-red-300"
                                                        : "border-slate-700 text-slate-500 hover:border-slate-600"
                                                }`}
                                            >
                                                {t === "all" ? "ทั้งหมด" : t === "stream" ? "LIVE เท่านั้น" : "VIDEO เท่านั้น"}
                                            </button>
                                        ))}
                                    </div>
                                    <p className="font-mono text-[10px] text-slate-500">
                                        {deleteType === "all"
                                            ? `ลบ job ทั้งหมด (LIVE + VIDEO) ของกล้อง ${selectedCam} รวมถึง prediction_results.json และรูปภาพ`
                                            : deleteType === "stream"
                                            ? `ลบเฉพาะ job ที่มาจาก live stream (job_id เริ่มด้วย live_) ของกล้อง ${selectedCam}`
                                            : `ลบเฉพาะ job ที่มาจาก video file ของกล้อง ${selectedCam}`}
                                    </p>
                                    <div className="flex items-center gap-3">
                                        <button
                                            disabled={deleting}
                                            onClick={async () => {
                                                if (!confirm(`ลบข้อมูลประเภท "${deleteType}" ของกล้อง "${selectedCam}"? ไม่สามารถกู้คืนได้`)) return;
                                                setDeleting(true);
                                                setDeleteMsg(null);
                                                try {
                                                    const res = await fetch(`${backendUrl}/api/json/camera/${encodeURIComponent(selectedCam)}?data_type=${deleteType}`, { method: "DELETE" });
                                                    const data = await res.json().catch(() => ({}));
                                                    if (!res.ok) throw new Error(data.detail || "Delete failed");
                                                    setDeleteMsg(`✓ ลบแล้ว ${data.deleted_count} job`);
                                                    await loadCameraJobs();
                                                } catch (e) {
                                                    setDeleteMsg(`✗ ${e instanceof Error ? e.message : "Error"}`);
                                                } finally {
                                                    setDeleting(false);
                                                    setTimeout(() => setDeleteMsg(null), 4000);
                                                }
                                            }}
                                            className="font-mono text-xs font-bold px-5 py-2 rounded-sm border border-red-500/60 bg-red-950/20 text-red-400 hover:bg-red-900/40 transition-all disabled:opacity-50"
                                        >
                                            {deleting ? "DELETING…" : "DELETE"}
                                        </button>
                                        {deleteMsg && (
                                            <span className={`font-mono text-xs ${deleteMsg.startsWith("✓") ? "text-green-400" : "text-red-400"}`}>
                                                {deleteMsg}
                                            </span>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </SettingsCard>
            </div>
        </div>
    );
}

// ─── Tab: Test ────────────────────────────────────────────────

type TestSubTab = "COLOR";

interface ColorItem {
  slot: string; cls: string; confidence: number; bbox: number[];
  detailed_colors: Record<string, number>;
  color_groups: Record<string, number>;
  primary_color: string; primary_group: string;
}
interface ColorPerson {
  track_id: number; bbox: number[]; confidence: number;
  stable_label: string; items: ColorItem[];
}
interface ColorResult {
  persons: ColorPerson[];
  annotated_image: string;
  width: number; height: number;
}

function TestTab({ backendUrl }: { backendUrl: string }) {
  const [subTab, setSubTab] = React.useState<TestSubTab>("COLOR");
  return (
    <div className="flex flex-col gap-4 w-full h-full">
      {/* sub-tab bar */}
      <div className="flex gap-2">
        {(["COLOR"] as TestSubTab[]).map((t) => (
          <button key={t} onClick={() => setSubTab(t)}
            className={`px-4 py-1.5 font-mono text-xs tracking-widest rounded-sm border transition-all ${
              subTab === t
                ? "border-cyan-500/60 bg-cyan-950/30 text-cyan-400"
                : "border-slate-700 text-slate-500 hover:border-slate-600 hover:text-slate-300"
            }`}>
            TEST {t}
          </button>
        ))}
      </div>
      {subTab === "COLOR" && <TestColorTab backendUrl={backendUrl} />}
    </div>
  );
}

const SLOT_COLORS: Record<string, string> = {
  top: "border-blue-500/60 text-blue-300",
  bottom: "border-orange-500/60 text-orange-300",
  dress: "border-purple-500/60 text-purple-300",
};

const COLOR_CSS: Record<string, string> = {
  red: "#e02020", dark_red: "#7a0a0a", crimson: "#be0f2f", scarlet: "#e8200a",
  maroon: "#5c0a0a", burgundy: "#6e1030",
  orange: "#f07020", dark_orange: "#a04010", amber: "#f0a010", peach: "#f8c090",
  coral: "#f06840",
  yellow: "#f0d020", gold: "#d4a020", light_yellow: "#f8f0a0", mustard: "#b09020",
  khaki: "#d0c880",
  green: "#30a030", dark_green: "#0a5010", light_green: "#80d080", olive: "#606820",
  lime: "#80d020", forest_green: "#1a5c20", mint: "#90f0b0", teal: "#208070",
  cyan: "#10d0e0", aqua: "#40d8e0",
  blue: "#2060d0", dark_blue: "#0a1870", light_blue: "#90b8f0", navy: "#0a1850",
  sky_blue: "#60b8f8", royal_blue: "#2040c8", cobalt: "#1830c0", turquoise: "#30b8d0",
  indigo: "#3020a0", denim: "#4060a0",
  purple: "#8030c0", dark_purple: "#4010a0", light_purple: "#c080f0",
  violet: "#7020d0", lavender: "#c0a0f0", magenta: "#d020c0", pink: "#f050a0",
  hot_pink: "#f01880", light_pink: "#f8b0d0", rose: "#f03060", salmon: "#f08070",
  white: "#f8f8f8", light_gray: "#c8c8c8", silver: "#b0b8c0", gray: "#808080",
  dark_gray: "#404040", black: "#181818", charcoal: "#2c2c2c",
  brown: "#7a4020", dark_brown: "#3a1808", tan: "#c89060", beige: "#e8d8b0",
  cream: "#f8f0d0", chocolate: "#5c2010",
  nude: "#d4a880", blush: "#f0a0a0",
};

function ColorSwatch({ name, size = 14 }: { name: string; size?: number }) {
  const css = COLOR_CSS[name];
  if (!css) return null;
  return (
    <span
      style={{ width: size, height: size, background: css, flexShrink: 0 }}
      className="inline-block rounded-sm border border-white/10 align-middle"
      title={name}
    />
  );
}

function TestColorTab({ backendUrl }: { backendUrl: string }) {
  const [imgSrc, setImgSrc] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<ColorResult | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [removeBg, setRemoveBg] = React.useState<boolean | null>(null); // null = use config
  const pasteAreaRef = React.useRef<HTMLDivElement>(null);

  // paste handler
  React.useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const item = Array.from(e.clipboardData?.items ?? []).find(
        (i) => i.type.startsWith("image/")
      );
      if (!item) return;
      const blob = item.getAsFile();
      if (!blob) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        setImgSrc(ev.target?.result as string);
        setResult(null);
        setError(null);
      };
      reader.readAsDataURL(blob);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, []);

  const handleFile = (file: File) => {
    if (!file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      setImgSrc(ev.target?.result as string);
      setResult(null);
      setError(null);
    };
    reader.readAsDataURL(file);
  };

  const analyze = async () => {
    if (!imgSrc) return;
    setLoading(true); setError(null); setResult(null);
    try {
      const body: Record<string, unknown> = { image: imgSrc };
      if (removeBg !== null) body.remove_bg = removeBg;
      const res = await fetch(`${backendUrl}/api/test/color-analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? "Analyze failed");
      }
      setResult(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid grid-cols-2 gap-6 w-full min-h-0">
      {/* LEFT: input */}
      <div className="flex flex-col gap-4">
        <SettingsCard title="IMAGE INPUT">
          {/* paste / drop zone */}
          <div
            ref={pasteAreaRef}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const f = e.dataTransfer.files[0];
              if (f) handleFile(f);
            }}
            onClick={() => {
              const inp = document.createElement("input");
              inp.type = "file"; inp.accept = "image/*";
              inp.onchange = () => { if (inp.files?.[0]) handleFile(inp.files[0]); };
              inp.click();
            }}
            className="relative border-2 border-dashed border-slate-700 hover:border-cyan-600/60 rounded-sm
                       flex flex-col items-center justify-center gap-3 cursor-pointer transition-all
                       bg-slate-900/40 hover:bg-cyan-950/10 min-h-[180px]"
          >
            {imgSrc ? (
              <img src={imgSrc} alt="input" className="max-h-64 max-w-full object-contain rounded" />
            ) : (
              <>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}
                  className="w-10 h-10 text-slate-600">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <circle cx="8.5" cy="8.5" r="1.5" />
                  <path d="M21 15l-5-5L5 21" />
                </svg>
                <p className="font-mono text-xs text-slate-500 text-center leading-relaxed">
                  PASTE image (Ctrl+V)<br />or DRAG & DROP / CLICK to browse
                </p>
              </>
            )}
          </div>

          {/* options */}
          <div className="flex items-center justify-between mt-1">
            <span className="font-mono text-[10px] text-slate-500">BG Removal Override</span>
            <div className="flex gap-1">
              {([null, true, false] as (boolean | null)[]).map((v) => (
                <button key={String(v)} onClick={() => setRemoveBg(v)}
                  className={`px-2 py-0.5 font-mono text-[10px] rounded-sm border transition-all ${
                    removeBg === v
                      ? "border-cyan-500/60 bg-cyan-950/30 text-cyan-300"
                      : "border-slate-700 text-slate-500 hover:border-slate-600"
                  }`}>
                  {v === null ? "CONFIG" : v ? "ON" : "OFF"}
                </button>
              ))}
            </div>
          </div>

          <button onClick={analyze} disabled={!imgSrc || loading}
            className="w-full font-mono text-xs font-bold py-2.5 rounded-sm border transition-all tracking-widest
                       border-cyan-500/60 bg-cyan-950/30 text-cyan-400
                       hover:bg-cyan-900/40 hover:border-cyan-400
                       disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2">
            {loading ? (
              <>
                <svg className="animate-spin w-3 h-3" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                ANALYZING…
              </>
            ) : "▶ ANALYZE"}
          </button>

          {error && (
            <div className="font-mono text-xs text-red-400 border border-red-800/40 bg-red-950/20 px-3 py-2 rounded-sm">
              ✗ {error}
            </div>
          )}
        </SettingsCard>

        {/* annotated result image */}
        {result && (
          <SettingsCard title={`RESULT — ${result.width}×${result.height} · ${result.persons.length} person(s)`}>
            <img src={result.annotated_image} alt="annotated" className="w-full rounded object-contain" />
          </SettingsCard>
        )}
      </div>

      {/* RIGHT: structured results */}
      <div className="flex flex-col gap-4 overflow-y-auto">
        {!result && !loading && (
          <div className="flex flex-col items-center justify-center h-48 gap-2 text-slate-700">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1} className="w-10 h-10">
              <path d="M9 17H5a2 2 0 00-2 2v2M5 3h14a2 2 0 012 2v4M3 7l9 6 9-6" />
            </svg>
            <p className="font-mono text-[10px] tracking-widest">PASTE AN IMAGE AND CLICK ANALYZE</p>
          </div>
        )}

        {result?.persons.map((person) => (
          <SettingsCard key={person.track_id}
            title={`PERSON ID:${person.track_id} — ${person.stable_label || "unknown"}`}>
            <div className="flex items-center gap-2 mb-2">
              <span className="font-mono text-[10px] text-slate-500">
                conf {(person.confidence * 100).toFixed(0)}%
              </span>
              <span className="font-mono text-[10px] text-slate-600">
                bbox [{person.bbox.join(", ")}]
              </span>
            </div>

            {person.items.length === 0 && (
              <p className="font-mono text-xs text-slate-600">No clothing detected</p>
            )}

            {person.items.map((item, idx) => (
              <div key={idx}
                className={`border rounded-sm p-3 space-y-2 ${SLOT_COLORS[item.slot] ?? "border-slate-700"}`}>
                {/* header */}
                <div className="flex items-center justify-between">
                  <span className={`font-mono text-[10px] uppercase tracking-widest font-bold ${
                    SLOT_COLORS[item.slot]?.split(" ")[1] ?? "text-slate-400"
                  }`}>
                    {item.slot.toUpperCase()}
                  </span>
                  <span className="font-mono text-xs text-slate-300">
                    {item.cls} <span className="text-slate-500">({(item.confidence * 100).toFixed(0)}%)</span>
                  </span>
                </div>

                {/* primary color */}
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[10px] text-slate-500">PRIMARY</span>
                  <ColorSwatch name={item.primary_color} size={16} />
                  <span className="font-mono text-xs text-white font-bold">{item.primary_color}</span>
                  <span className="font-mono text-[10px] text-slate-500">({item.primary_group})</span>
                </div>

                {/* color bar */}
                {Object.keys(item.detailed_colors).length > 0 && (
                  <div>
                    <p className="font-mono text-[9px] text-slate-600 mb-1">DETAILED COLORS</p>
                    <div className="flex rounded-sm overflow-hidden h-5">
                      {Object.entries(item.detailed_colors)
                        .sort((a, b) => b[1] - a[1])
                        .map(([name, pct]) => (
                          <div key={name}
                            style={{ width: `${pct}%`, background: COLOR_CSS[name] ?? "#555" }}
                            title={`${name}: ${pct.toFixed(1)}%`}
                            className="border-r border-black/20 last:border-0" />
                        ))}
                    </div>
                    <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1.5">
                      {Object.entries(item.detailed_colors)
                        .sort((a, b) => b[1] - a[1])
                        .map(([name, pct]) => (
                          <span key={name} className="flex items-center gap-1 font-mono text-[9px] text-slate-300">
                            <ColorSwatch name={name} size={10} />
                            {name} {pct.toFixed(1)}%
                          </span>
                        ))}
                    </div>
                  </div>
                )}

                {/* color groups */}
                {Object.keys(item.color_groups).length > 0 && (
                  <div>
                    <p className="font-mono text-[9px] text-slate-600 mb-1">COLOR GROUPS</p>
                    <div className="flex flex-wrap gap-1">
                      {Object.entries(item.color_groups)
                        .sort((a, b) => b[1] - a[1])
                        .map(([grp, pct]) => (
                          <span key={grp}
                            className="font-mono text-[9px] px-1.5 py-0.5 rounded-sm bg-slate-800 text-slate-400 border border-slate-700">
                            {grp} {pct.toFixed(0)}%
                          </span>
                        ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </SettingsCard>
        ))}
      </div>
    </div>
  );
}

// ─── Shared UI Atoms ──────────────────────────────────────────

function SettingsCard({ title, modified = false, children }: {
    title: string; modified?: boolean; children: React.ReactNode;
}) {
    return (
        <div className={`hud-panel p-5 flex flex-col gap-3 transition-all ${modified ? "ring-1 ring-amber-700/30" : ""}`}>
            <div className="flex items-center gap-3 mb-1">
                <div className="font-mono text-xs tracking-[0.25em] text-orange-500 font-bold">◈ {title}</div>
                {modified && (
                    <span className="font-mono text-xs text-amber-400/80 border border-amber-700/40 bg-amber-950/20 px-2 py-0.5 rounded-sm">MODIFIED</span>
                )}
            </div>
            {children}
        </div>
    );
}

function ResetTabBar({ label, onReset, resetting }: { label: string; onReset: () => void; resetting: boolean }) {
    return (
        <div className="w-full mt-5 flex items-center justify-end gap-3 border-t border-slate-800/40 pt-4">
            <span className="font-mono text-xs text-slate-600 tracking-widest mr-auto">
                Reset only the settings visible in this tab ({label})
            </span>
            <button
                onClick={onReset}
                disabled={resetting}
                className="font-mono text-xs font-bold px-5 py-2 rounded-sm border border-slate-600/60 bg-slate-900/40 text-slate-400
                    hover:bg-slate-800/60 hover:border-orange-500/40 hover:text-orange-300 transition-all disabled:opacity-30 tracking-widest"
            >
                {resetting ? "RESTORING…" : "↺ RESET THIS TAB"}
            </button>
        </div>
    );
}

function DefaultHint({ value }: { value: string | number | boolean }) {
    return (
        <div className="font-mono text-xs text-slate-500 mt-1">
            <span className="text-slate-600">default:</span> <span className="text-slate-400">{String(value)}</span>
        </div>
    );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
    return <div className="font-mono text-xs text-slate-500 tracking-widest mb-1.5 uppercase font-semibold">{children}</div>;
}

function InfoRow({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
    return (
        <div className="flex items-center justify-between py-2 border-b border-slate-800/40 last:border-0">
            <span className="font-mono text-xs text-slate-500 tracking-widest">{label}</span>
            <span className={`font-mono text-sm font-bold ${highlight ? "text-green-400" : "text-slate-200"}`}>{value}</span>
        </div>
    );
}

function StatusBadge({ exists, size }: { exists: boolean; size: number | null | undefined }) {
    return (
        <div className={`inline-flex items-center gap-2 mt-2 px-3 py-1 rounded-sm border text-xs font-mono font-semibold ${exists ? "border-green-700/40 bg-green-950/20 text-green-400" : "border-red-700/40 bg-red-950/20 text-red-400"}`}>
            <div className={`w-2 h-2 rounded-full ${exists ? "bg-green-400 animate-pulse" : "bg-red-500"}`} />
            {exists ? `LOADED${size ? ` · ${size} MB` : ""}` : "FILE NOT FOUND"}
        </div>
    );
}

function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
    return (
        <button onClick={() => onChange(!value)} className="flex items-center gap-3 group transition-all">
            <div className={`relative w-10 h-5 rounded-full border transition-colors ${value ? "border-orange-500/60 bg-orange-950/40" : "border-slate-700 bg-slate-900"}`}>
                <div className={`absolute top-0.5 w-4 h-4 rounded-full transition-all ${value ? "left-5 bg-orange-400" : "left-0.5 bg-slate-600"}`} />
            </div>
            <span className={`font-mono text-xs tracking-widest font-semibold ${value ? "text-orange-400" : "text-slate-500"}`}>{label}</span>
        </button>
    );
}

function SliderField({
    label, description, value, min, max, step, display, onChange, defaultValue, modified,
}: {
    label: string; description: string; value: number; min: number; max: number; step: number;
    display: (v: number) => string; onChange: (v: number) => void;
    defaultValue?: number; modified?: boolean;
}) {
    return (
        <div>
            <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                    <FieldLabel>{label}</FieldLabel>
                    {modified && <span className="font-mono text-xs text-amber-400">✎</span>}
                </div>
                <div className="flex items-center gap-3">
                    {modified && defaultValue !== undefined && (
                        <span className="font-mono text-xs text-slate-500">default: {display(defaultValue)}</span>
                    )}
                    <span className={`font-mono text-lg font-bold ${modified ? "text-amber-400" : "text-orange-400"}`}>{display(value)}</span>
                </div>
            </div>
            <input
                type="range" min={min} max={max} step={step} value={value}
                onChange={(e) => onChange(parseFloat(e.target.value))}
                className={`w-full h-1.5 appearance-none rounded-full outline-none cursor-pointer ${modified ? "bg-amber-950/40" : "bg-slate-800"}
          [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4
          [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:cursor-pointer
          ${modified
                        ? "[&::-webkit-slider-thumb]:bg-amber-400 [&::-webkit-slider-thumb]:shadow-[0_0_8px_rgba(251,191,36,0.7)]"
                        : "[&::-webkit-slider-thumb]:bg-orange-400 [&::-webkit-slider-thumb]:shadow-[0_0_8px_rgba(251,146,60,0.7)]"
                    }`}
            />
            <div className="flex justify-between mt-1">
                <span className="font-mono text-xs text-slate-600">{display(min)}</span>
                <span className="font-mono text-xs text-slate-600">{description}</span>
                <span className="font-mono text-xs text-slate-600">{display(max)}</span>
            </div>
        </div>
    );
}
