"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";

// ─── Types ────────────────────────────────────────────────────
interface SystemConfig {
    detector_model: string;
    classifier_model: string;
    detection_confidence: number;
    iou_threshold: number;
    max_tracks: number;
    frame_skip: number;
    detection_enabled: boolean;
    classification_enabled: boolean;
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

type Tab = "MODELS" | "DETECTION" | "SYSTEM" | "DATABASE";

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

    const fetchData = useCallback(async () => {
        setLoading(true);
        try {
            const [settingsRes, modelsRes] = await Promise.all([
                fetch("/api/settings"),
                fetch("/api/settings/models"),
            ]);
            if (settingsRes.ok) {
                const d = await settingsRes.json();
                setData(d);
                setDraft(d.config);
                setModifiedKeys(d.modified_keys ?? []);
            }
            if (modelsRes.ok) {
                const m = await modelsRes.json();
                setModelFiles(m.models ?? []);
            }
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchData(); }, [fetchData]);

    const handleSave = async () => {
        setSaving(true);
        setSaveMsg(null);
        try {
            const res = await fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(draft),
            });
            if (res.ok) {
                setSaveMsg("✓ SAVED");
                await fetchData();
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
                await fetchData();
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
            const res = await fetch("/api/settings/models", { method: "POST", body: form });
            const json = await res.json();
            if (res.ok) {
                setUploadStatus("done");
                setUploadMsg(`✓ ${json.name} uploaded (${json.size_mb} MB)`);
                await fetchData();
            } else {
                setUploadStatus("error");
                setUploadMsg(json.error ?? "Upload failed");
            }
        } catch {
            setUploadStatus("error");
            setUploadMsg("Network error");
        }
    };

    const tabs: Tab[] = ["MODELS", "DETECTION", "SYSTEM", "DATABASE"];

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
                        {activeTab === "SYSTEM" && <SystemTab data={data} />}
                        {activeTab === "DATABASE" && <DatabaseTab />}
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

// ─── Tab: System Info ─────────────────────────────────────────
function SystemTab({ data }: { data: SettingsData | null }) {
    if (!data) return null;
    const hw = data.hardware;
    return (
        <div className="grid grid-cols-3 gap-6 w-full">
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
                            const isModified = data.modified_keys.includes(k);
                            const defaultVal = data.defaults[k as keyof SystemConfig];
                            return (
                                <div key={k} className={`border rounded-sm p-4 ${isModified ? "bg-amber-950/20 border-amber-700/40" : "bg-slate-900/40 border-slate-800"}`}>
                                    <div className={`font-mono text-xs tracking-widest uppercase mb-1 flex items-center gap-1 ${isModified ? "text-amber-600" : "text-slate-500"}`}>
                                        {k.replaceAll("_", " ")}
                                        {isModified && <span className="text-amber-400">✎</span>}
                                    </div>
                                    <div className={`font-mono text-base font-bold ${isModified ? "text-amber-400" : "text-orange-400"}`}>{String(v)}</div>
                                    {isModified && (
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
function DatabaseTab() {
    const [stats, setStats] = useState<{ detections: number; videos: number; cameras: number } | null>(null);
    const [purging, setPurging] = useState(false);
    const [purgeMsg, setPurgeMsg] = useState<string | null>(null);
    const backendUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

    useEffect(() => {
        Promise.all([
            fetch("/api/video/detections?limit=1").then((r) => r.json()).catch(() => null),
            fetch("/api/video/videos").then((r) => r.json()).catch(() => null),
            fetch(`${backendUrl}/api/cameras`).then((r) => r.json()).catch(() => null),
        ]).then(([det, vids, cams]) => {
            setStats({
                detections: Array.isArray(det) ? det.length : 0,
                videos: Array.isArray(vids) ? vids.length : 0,
                cameras: Array.isArray(cams?.cameras) ? cams.cameras.length : 0,
            });
        });
    }, [backendUrl]);

    return (
        <div className="grid grid-cols-2 gap-6 w-full">
            <SettingsCard title="CONNECTION">
                <InfoRow label="HOST" value="localhost:5432" />
                <InfoRow label="DATABASE" value="cctv_analytics" />
                <InfoRow label="ORM" value="psycopg2 (raw SQL)" />
                <InfoRow label="OBJECT STORE" value="MinIO" />
            </SettingsCard>

            <SettingsCard title="DATA SUMMARY">
                <InfoRow label="DETECTIONS" value={stats ? String(stats.detections) : "…"} />
                <InfoRow label="VIDEOS" value={stats ? String(stats.videos) : "…"} />
                <InfoRow label="CAMERAS" value={stats ? String(stats.cameras) : "…"} />
            </SettingsCard>

            <div className="col-span-2">
                <SettingsCard title="MAINTENANCE">
                    <div className="flex gap-6 items-center">
                        <div className="flex-1">
                            <FieldLabel>PURGE DETECTIONS</FieldLabel>
                            <p className="font-mono text-sm text-slate-500 mt-1">
                                Delete all detection records from the database. This cannot be undone.
                            </p>
                        </div>
                        <button
                            onClick={async () => {
                                if (!confirm("Delete ALL detection records? This cannot be undone.")) return;
                                setPurging(true);
                                setPurgeMsg(null);
                                await new Promise((r) => setTimeout(r, 1200));
                                setPurging(false);
                                setPurgeMsg("Not yet implemented — please run manually via SQL");
                                setTimeout(() => setPurgeMsg(null), 4000);
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
