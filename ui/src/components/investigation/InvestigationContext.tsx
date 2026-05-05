"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useReducer,
  useRef,
} from "react";
import type {
  ClothingClass,
  ClothingColor,
  SearchFilters,
  SearchResult,
  AttributeDetectionResult,
  ToneGroup,
  ClothingColorGroup,
  DetailedColor,
  AdvancedFilter,
} from "@/types";
import { API } from "@/lib/api"; // FastAPI base URL จาก .env.local (NEXT_PUBLIC_API_URL)

// ─── State ────────────────────────────────────────────────────

interface InvestigationState {
  filters: SearchFilters;
  results: SearchResult[];
  total: number;
  page: number;
  hasMore: boolean;
  isSearching: boolean;
  isLoadingMore: boolean;
  autoFillImage: string | null;
  autoFillStatus: "idle" | "analyzing" | "done" | "error";
  autoFillResult: AttributeDetectionResult | null;
  // Trace modal
  traceTarget: SearchResult | null;
  // Image modal
  imageTarget: SearchResult | null;
  // Detection detail
  detectionDetail: any | null;
  // Advanced search
  advancedFilters: AdvancedFilter[];
  advancedMode: boolean;
  globalClothingLogic: "OR" | "AND";
  isAdvancedModalOpen: boolean;
}

const INITIAL_FILTERS: SearchFilters = {
  clothing: [],
  colors: [],
  logic: "OR",
  threshold: 0.1,
  camera_id: undefined,
  video_id: undefined,
  start_time: undefined,
  end_time: undefined,
  // Secondary color filters (tone groups calculated on-the-fly from detailed_colors)
  temperature: undefined,
  brightness: undefined,
  vibrancy: undefined,
  clothing_groups: [],
};

const INITIAL_STATE: InvestigationState = {
  filters: INITIAL_FILTERS,
  results: [],
  total: 0,
  page: 1,
  hasMore: false,
  isSearching: false,
  isLoadingMore: false,
  autoFillImage: null,
  autoFillStatus: "idle",
  autoFillResult: null,
  traceTarget: null,
  imageTarget: null,
  detectionDetail: null,
  advancedFilters: [],
  advancedMode: false,
  globalClothingLogic: "OR",
  isAdvancedModalOpen: false,
};

// ─── Actions ──────────────────────────────────────────────────

type Action =
  | { type: "SET_CLOTHING"; payload: ClothingClass[] }
  | { type: "TOGGLE_CLOTHING"; payload: ClothingClass }
  | { type: "SET_COLORS"; payload: ClothingColor[] }
  | { type: "TOGGLE_COLOR"; payload: ClothingColor }
  | { type: "SET_LOGIC"; payload: "OR" | "AND" }
  | { type: "SET_THRESHOLD"; payload: number }
  | { type: "SET_CAMERA"; payload: string | undefined }
  | { type: "SET_VIDEO"; payload: string | undefined }
  | { type: "SET_START_TIME"; payload: string | undefined }
  | { type: "SET_END_TIME"; payload: string | undefined }
  | { type: "SET_TEMPERATURE"; payload: "warm" | "cool" | "neutral" | undefined }
  | { type: "SET_BRIGHTNESS"; payload: "light" | "dark" | "medium" | undefined }
  | { type: "SET_VIBRANCY"; payload: "vibrant" | "muted" | "pastel" | undefined }
  | { type: "SET_CLOTHING_GROUPS"; payload: ClothingColorGroup[] }
  | { type: "TOGGLE_CLOTHING_GROUP"; payload: ClothingColorGroup }
  | { type: "RESET_FILTERS" }
  | { type: "SEARCH_START" }
  | { type: "SEARCH_SUCCESS"; payload: { results: SearchResult[]; total: number; hasMore: boolean } }
  | { type: "SEARCH_ERROR" }
  | { type: "LOAD_MORE_START" }
  | { type: "LOAD_MORE_SUCCESS"; payload: { results: SearchResult[]; hasMore: boolean } }
  | { type: "SET_AUTOFILL_IMAGE"; payload: string }
  | { type: "AUTOFILL_START" }
  | { type: "AUTOFILL_SUCCESS"; payload: AttributeDetectionResult }
  | { type: "AUTOFILL_ERROR" }
  | { type: "CLEAR_AUTOFILL" }
  | { type: "OPEN_TRACE"; payload: SearchResult }
  | { type: "CLOSE_TRACE" }
  | { type: "OPEN_IMAGE"; payload: SearchResult }
  | { type: "CLOSE_IMAGE" }
  | { type: "SET_DETECTION_DETAIL"; payload: any | null }
  // Advanced search actions
  | { type: "OPEN_ADVANCED_MODAL" }
  | { type: "CLOSE_ADVANCED_MODAL" }
  | { type: "ADD_ADVANCED_FILTER"; payload: AdvancedFilter }
  | { type: "REMOVE_ADVANCED_FILTER"; payload: ClothingClass }
  | { type: "UPDATE_ADVANCED_FILTER"; payload: AdvancedFilter }
  | { type: "SET_GLOBAL_CLOTHING_LOGIC"; payload: "OR" | "AND" }
  | { type: "CLEAR_ADVANCED_FILTERS" }
  | { type: "APPLY_ADVANCED_SEARCH" }
  | { type: "SET_ADVANCED_MODE"; payload: boolean };

function reducer(state: InvestigationState, action: Action): InvestigationState {
  switch (action.type) {
    case "TOGGLE_CLOTHING": {
      const has = state.filters.clothing.includes(action.payload);
      return {
        ...state,
        filters: {
          ...state.filters,
          clothing: has
            ? state.filters.clothing.filter((c) => c !== action.payload)
            : [...state.filters.clothing, action.payload],
        },
      };
    }
    case "SET_CLOTHING":
      return { ...state, filters: { ...state.filters, clothing: action.payload } };
    case "TOGGLE_COLOR": {
      const has = state.filters.colors.includes(action.payload);
      return {
        ...state,
        filters: {
          ...state.filters,
          colors: has
            ? state.filters.colors.filter((c) => c !== action.payload)
            : [...state.filters.colors, action.payload],
        },
      };
    }
    case "SET_COLORS":
      return { ...state, filters: { ...state.filters, colors: action.payload } };
    case "SET_LOGIC":
      return { ...state, filters: { ...state.filters, logic: action.payload } };
    case "SET_THRESHOLD":
      return { ...state, filters: { ...state.filters, threshold: action.payload } };
    case "SET_CAMERA":
      return { ...state, filters: { ...state.filters, camera_id: action.payload, video_id: undefined } };
    case "SET_VIDEO":
      return { ...state, filters: { ...state.filters, video_id: action.payload } };
    case "SET_START_TIME":
      return { ...state, filters: { ...state.filters, start_time: action.payload } };
    case "SET_END_TIME":
      return { ...state, filters: { ...state.filters, end_time: action.payload } };
    case "SET_TEMPERATURE":
      return { ...state, filters: { ...state.filters, temperature: action.payload } };
    case "SET_BRIGHTNESS":
      return { ...state, filters: { ...state.filters, brightness: action.payload } };
    case "SET_VIBRANCY":
      return { ...state, filters: { ...state.filters, vibrancy: action.payload } };
    case "TOGGLE_CLOTHING_GROUP": {
      const has = state.filters.clothing_groups?.includes(action.payload);
      return {
        ...state,
        filters: {
          ...state.filters,
          clothing_groups: has
            ? state.filters.clothing_groups?.filter((g) => g !== action.payload) || []
            : [...(state.filters.clothing_groups || []), action.payload],
        },
      };
    }
    case "SET_CLOTHING_GROUPS":
      return { ...state, filters: { ...state.filters, clothing_groups: action.payload } };
    case "RESET_FILTERS":
      return { ...state, filters: INITIAL_FILTERS, autoFillImage: null, autoFillStatus: "idle", autoFillResult: null };
    case "SEARCH_START":
      return { ...state, isSearching: true, page: 1 };
    case "SEARCH_SUCCESS":
      return {
        ...state,
        isSearching: false,
        results: action.payload.results,
        total: action.payload.total,
        hasMore: action.payload.hasMore,
        page: 1,
      };
    case "SEARCH_ERROR":
      return { ...state, isSearching: false };
    case "LOAD_MORE_START":
      return { ...state, isLoadingMore: true };
    case "LOAD_MORE_SUCCESS":
      return {
        ...state,
        isLoadingMore: false,
        results: [...state.results, ...action.payload.results],
        hasMore: action.payload.hasMore,
        page: state.page + 1,
      };
    case "SET_AUTOFILL_IMAGE":
      return { ...state, autoFillImage: action.payload };
    case "AUTOFILL_START":
      return { ...state, autoFillStatus: "analyzing" };
    case "AUTOFILL_SUCCESS":
      return { ...state, autoFillStatus: "done", autoFillResult: action.payload };
    case "AUTOFILL_ERROR":
      return { ...state, autoFillStatus: "error" };
    case "CLEAR_AUTOFILL":
      return { ...state, autoFillImage: null, autoFillStatus: "idle", autoFillResult: null };
    case "OPEN_TRACE":
      return { ...state, traceTarget: action.payload };
    case "CLOSE_TRACE":
      return { ...state, traceTarget: null };
    case "OPEN_IMAGE":
      return { ...state, imageTarget: action.payload };
    case "CLOSE_IMAGE":
      return { ...state, imageTarget: null };
    case "SET_DETECTION_DETAIL":
      return { ...state, detectionDetail: action.payload };
    // Advanced search reducer cases
    case "OPEN_ADVANCED_MODAL":
      return { ...state, isAdvancedModalOpen: true };
    case "CLOSE_ADVANCED_MODAL":
      return { ...state, isAdvancedModalOpen: false };
    case "ADD_ADVANCED_FILTER": {
      const existingIndex = state.advancedFilters.findIndex(
        (f) => f.clothing === action.payload.clothing
      );
      if (existingIndex >= 0) {
        // Update existing filter
        const newFilters = [...state.advancedFilters];
        newFilters[existingIndex] = action.payload;
        return { ...state, advancedFilters: newFilters };
      }
      return {
        ...state,
        advancedFilters: [...state.advancedFilters, action.payload],
      };
    }
    case "REMOVE_ADVANCED_FILTER":
      return {
        ...state,
        advancedFilters: state.advancedFilters.filter(
          (f) => f.clothing !== action.payload
        ),
      };
    case "UPDATE_ADVANCED_FILTER": {
      const index = state.advancedFilters.findIndex(
        (f) => f.clothing === action.payload.clothing
      );
      if (index >= 0) {
        const newFilters = [...state.advancedFilters];
        newFilters[index] = action.payload;
        return { ...state, advancedFilters: newFilters };
      }
      return state;
    }
    case "SET_GLOBAL_CLOTHING_LOGIC":
      return { ...state, globalClothingLogic: action.payload };
    case "CLEAR_ADVANCED_FILTERS":
      return { ...state, advancedFilters: [], advancedMode: false };
    case "APPLY_ADVANCED_SEARCH":
      return {
        ...state,
        advancedMode: state.advancedFilters.length > 0,
        isAdvancedModalOpen: false,
        // Reset page and trigger search flag
        page: 1,
      };
    case "SET_ADVANCED_MODE":
      return { ...state, advancedMode: action.payload };
    default:
      return state;
  }
}

// ─── Context ──────────────────────────────────────────────────

interface InvestigationContextValue {
  state: InvestigationState;
  dispatch: React.Dispatch<Action>;
  // Auto-fill state (exposed for DebugPanel)
  autoFillImage: string | null;
  autoFillStatus: "idle" | "analyzing" | "done" | "error";
  autoFillResult: AttributeDetectionResult | null;
  // Helper actions
  toggleClothing: (c: ClothingClass) => void;
  toggleColor: (c: ClothingColor) => void;
  setLogic: (l: "OR" | "AND") => void;
  setThreshold: (t: number) => void;
  setCamera: (id: string | undefined) => void;
  setVideo: (id: string | undefined) => void;
  setTimeRange: (start?: string, end?: string) => void;
  setTemperature: (t: "warm" | "cool" | "neutral" | undefined) => void;
  setBrightness: (b: "light" | "dark" | "medium" | undefined) => void;
  setVibrancy: (v: "vibrant" | "muted" | "pastel" | undefined) => void;
  toggleClothingGroup: (g: ClothingColorGroup) => void;
  resetFilters: () => void;
  runSearch: () => void;
  loadMore: () => void;
  submitAutoFill: (file: File) => void;
  clearAutoFill: () => void;
  openTrace: (result: SearchResult) => void;
  closeTrace: () => void;
  openImage: (result: SearchResult) => void;
  closeImage: () => void;
  setDetectionDetail: (detail: any | null) => void;
  // Advanced search helpers
  openAdvancedModal: () => void;
  closeAdvancedModal: () => void;
  addAdvancedFilter: (filter: AdvancedFilter) => void;
  removeAdvancedFilter: (clothing: ClothingClass) => void;
  updateAdvancedFilter: (filter: AdvancedFilter) => void;
  setGlobalClothingLogic: (logic: "OR" | "AND") => void;
  clearAdvancedFilters: () => void;
  applyAdvancedSearch: () => void;
  runAdvancedSearch: () => void;
}

const InvestigationContext = createContext<InvestigationContextValue | null>(null);

export function useInvestigation() {
  const ctx = useContext(InvestigationContext);
  if (!ctx) throw new Error("useInvestigation must be used inside InvestigationProvider");
  return ctx;
}

// ─── Provider ────────────────────────────────────────────────

export function InvestigationProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
  const searchAbortRef = useRef<AbortController | null>(null);

  // ── Auto search on mount ───────────────────────────────────
  useEffect(() => {
    // Auto search with default filters on component mount
    const timer = setTimeout(() => {
      runSearch();
    }, 500); // Small delay to ensure component is mounted

    return () => clearTimeout(timer);
  }, []);

  // ── Fetch detection detail when imageTarget changes ────────────────────────────────────
  useEffect(() => {
    if (!state.imageTarget) {
      dispatch({ type: "SET_DETECTION_DETAIL", payload: null });
      return;
    }

    const fetchDetectionDetail = async () => {
      try {
        // เรียก FastAPI โดยตรง — ดึง detection detail
        const response = await fetch(`${API}/api/detections/${encodeURIComponent(state.imageTarget!.id)}`);
        if (!response.ok) {
          throw new Error("Failed to fetch detection details");
        }
        const data = await response.json();
        dispatch({ type: "SET_DETECTION_DETAIL", payload: data });
      } catch (error) {
        console.error("Error fetching detection detail:", error);
        dispatch({ type: "SET_DETECTION_DETAIL", payload: null });
      }
    };

    fetchDetectionDetail();
  }, [state.imageTarget]);

  // ── Search ──────────────────────────────────────────────────
  const runSearch = useCallback(async () => {
    searchAbortRef.current?.abort();
    const controller = new AbortController();
    searchAbortRef.current = controller;

    dispatch({ type: "SEARCH_START" });

    try {
      const params = buildParams(state.filters, 1);
      // เรียก FastAPI /api/search/persons โดยตรง — ไม่ผ่าน Next.js transform layer
      const res = await fetch(`${API}/api/search/persons?${params}`, {
        signal: controller.signal,
      });
      if (!res.ok) throw new Error("Search failed");
      const data = await res.json();
      dispatch({
        type: "SEARCH_SUCCESS",
        payload: {
          results: data.results,
          total: data.total,
          hasMore: data.has_more,
        },
      });
    } catch (e: unknown) {
      if (e instanceof Error && e.name !== "AbortError") {
        dispatch({ type: "SEARCH_ERROR" });
      }
    }
  }, [state.filters]);

  // ── Load more (infinite scroll) ──────────────────────────────
  const loadMore = useCallback(async () => {
    if (state.isLoadingMore || !state.hasMore) return;
    dispatch({ type: "LOAD_MORE_START" });

    try {
      if (state.advancedMode && state.advancedFilters.length > 0) {
        // Load more for advanced search
        const body = {
          clothing_groups: state.advancedFilters.map(f => ({
            clothing: f.clothing,
            colors: f.includeWithoutColors && f.colors.length === 0 ? [] : f.colors,
            color_logic: f.colorLogic,
          })),
          global_logic: state.globalClothingLogic,
          threshold: state.filters.threshold,
          camera_id: state.filters.camera_id,
          video_id: state.filters.video_id,
          start_time: state.filters.start_time,
          end_time: state.filters.end_time,
        };
        const res = await fetch(`${API}/api/search/advanced?page=${state.page + 1}&limit=24`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error("Load more failed");
        const data = await res.json();
        dispatch({
          type: "LOAD_MORE_SUCCESS",
          payload: { results: data.results, hasMore: data.has_more },
        });
      } else {
        // Load more for normal search
        const params = buildParams(state.filters, state.page + 1);
        const res = await fetch(`${API}/api/search/persons?${params}`);
        if (!res.ok) throw new Error("Load more failed");
        const data = await res.json();
        dispatch({
          type: "LOAD_MORE_SUCCESS",
          payload: { results: data.results, hasMore: data.has_more },
        });
      }
    } catch {
      dispatch({ type: "LOAD_MORE_START" }); // reset flag
    }
  }, [state.filters, state.page, state.isLoadingMore, state.hasMore, state.advancedMode, state.advancedFilters, state.globalClothingLogic]);

  // ── Auto-fill ────────────────────────────────────────────────
  const submitAutoFill = useCallback(async (file: File) => {
    // Preview
    const dataUrl = await fileToDataUrl(file);
    dispatch({ type: "SET_AUTOFILL_IMAGE", payload: dataUrl });
    dispatch({ type: "AUTOFILL_START" });

    try {
      const form = new FormData();
      form.append("image", file);
      const res = await fetch("/api/search/detect-attributes", {
        method: "POST",
        body: form,
      });
      if (!res.ok) throw new Error("Detection failed");
      const result: AttributeDetectionResult = await res.json();

      // Log API response
      console.log("[CONTEXT] API response received:", result);
      console.log("[CONTEXT] detected_attributes:", result.detected_attributes);
      console.log("[CONTEXT] all_items:", result.all_items);

      dispatch({ type: "AUTOFILL_SUCCESS", payload: result });

      // ── Auto-apply detected attributes to filters ──
      // Extract from detected_attributes (API response structure)
      const detectedClass = result.detected_attributes?.class_name;
      const detectedColor = result.detected_attributes?.color_name;
      const allItems = result.all_items || [];

      console.log("[CONTEXT] Parsed detected_class:", detectedClass, "detected_color:", detectedColor, "all_items count:", allItems.length);
      
      // Get unique colors from all_items
      const uniqueColors = [...new Set(
        allItems
          .filter((item: any) => item.color && item.color !== "Unknown")
          .map((item: any) => item.color)
      )];
      
      if (detectedClass && detectedClass !== "Unknown") {
        dispatch({ type: "SET_CLOTHING", payload: [detectedClass as ClothingClass] });
      }
      if (uniqueColors.length > 0) {
        dispatch({ type: "SET_COLORS", payload: uniqueColors as ClothingColor[] });
      }

      // ── Use Advanced Search with Relevance Sorting ──
      const clothingGroups: AdvancedFilter[] = [];
      if (detectedClass && detectedClass !== "Unknown") {
        clothingGroups.push({
          clothing: detectedClass as ClothingClass,
          colors: detectedColor && detectedColor !== "Unknown" ? [detectedColor as any] : [],
          colorLogic: "OR",
          includeWithoutColors: false,
        });
      }
      const bottomItem = allItems.find((item: any) => item.category === "BOTTOM");
      if (bottomItem && bottomItem.class_name && bottomItem.class_name !== "Unknown") {
        clothingGroups.push({
          clothing: bottomItem.class_name as ClothingClass,
          colors: bottomItem.color && bottomItem.color !== "Unknown" ? [bottomItem.color as any] : [],
          colorLogic: "OR",
          includeWithoutColors: false,
        });
      }
      
      if (clothingGroups.length > 0) {
        setTimeout(() => {
          dispatch({ type: "SEARCH_START" });
          const body = {
            clothing_groups: clothingGroups.map(f => ({
              clothing: f.clothing,
              colors: f.colors,
              color_logic: f.colorLogic,
            })),
            global_logic: "OR" as const,
            threshold: state.filters.threshold,
            camera_id: state.filters.camera_id,
            video_id: state.filters.video_id,
            start_time: state.filters.start_time,
            end_time: state.filters.end_time,
          };
          
          fetch(`${API}/api/search/advanced?page=1&limit=24`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          })
            .then((r) => r.json())
            .then((data) => {
              dispatch({
                type: "SEARCH_SUCCESS",
                payload: { results: data.results, total: data.total, hasMore: data.has_more },
              });
            })
            .catch(() => dispatch({ type: "SEARCH_ERROR" }));
        }, 300);
      }
    } catch {
      dispatch({ type: "AUTOFILL_ERROR" });
    }
  }, [state.filters]);

  // ─── Utils ────────────────────────────────────────────────────

  function buildParams(filters: SearchFilters, page: number): string {
    const p = new URLSearchParams();
    filters.clothing.forEach((c) => p.append("clothing[]", c));
    filters.colors.forEach((c) => p.append("colors[]", c));
    p.set("logic", filters.logic);
    p.set("threshold", filters.threshold.toString());
    p.set("page", page.toString());
    p.set("limit", "24");
    if (filters.camera_id) p.set("camera_id", filters.camera_id);
    if (filters.video_id) p.set("video_id", filters.video_id);
    if (filters.start_time) p.set("start_time", filters.start_time);
    if (filters.end_time) p.set("end_time", filters.end_time);
    // Secondary color filters
    if (filters.temperature) p.set("temperature", filters.temperature);
    if (filters.brightness) p.set("brightness", filters.brightness);
    if (filters.vibrancy) p.set("vibrancy", filters.vibrancy);
    filters.clothing_groups?.forEach((g) => p.append("clothing_groups[]", g));

    return p.toString();
  }

  function fileToDataUrl(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result as string);
      r.onerror = () => reject(new Error("Read failed"));
      r.readAsDataURL(file);
    });
  }

  // ── Advanced Search ──────────────────────────────────────────
  const runAdvancedSearch = useCallback(async () => {
    if (!state.advancedMode || state.advancedFilters.length === 0) return;

    searchAbortRef.current?.abort();
    const controller = new AbortController();
    searchAbortRef.current = controller;

    dispatch({ type: "SEARCH_START" });

    try {
      const body = {
        clothing_groups: state.advancedFilters.map(f => ({
          clothing: f.clothing,
          // If includeWithoutColors is true, send empty colors array (backend will match any color)
          colors: f.includeWithoutColors && f.colors.length === 0 ? [] : f.colors,
          color_logic: f.colorLogic,
        })),
        global_logic: state.globalClothingLogic,
        threshold: state.filters.threshold,
        camera_id: state.filters.camera_id,
        video_id: state.filters.video_id,
        start_time: state.filters.start_time,
        end_time: state.filters.end_time,
      };

      const res = await fetch(`${API}/api/search/advanced?page=${state.page}&limit=24`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!res.ok) throw new Error("Advanced search failed");
      const data = await res.json();
      dispatch({
        type: "SEARCH_SUCCESS",
        payload: {
          results: data.results,
          total: data.total,
          hasMore: data.has_more,
        },
      });
    } catch (e: unknown) {
      if (e instanceof Error && e.name !== "AbortError") {
        dispatch({ type: "SEARCH_ERROR" });
      }
    }
  }, [state.advancedFilters, state.globalClothingLogic, state.filters, state.advancedMode]);

  // ── Trigger advanced search when advancedMode becomes true ───────────────────
  const prevAdvancedModeRef = useRef(state.advancedMode);
  useEffect(() => {
    // When advancedMode transitions from false to true, trigger the search
    if (state.advancedMode && !prevAdvancedModeRef.current && state.advancedFilters.length > 0) {
      // Use a small delay to ensure all state updates are committed
      const timer = setTimeout(() => {
        runAdvancedSearch();
      }, 50);
      return () => clearTimeout(timer);
    }
    prevAdvancedModeRef.current = state.advancedMode;
  }, [state.advancedMode, state.advancedFilters.length, runAdvancedSearch]);

  const value: InvestigationContextValue = {
    state,
    dispatch,
    autoFillImage: state.autoFillImage,
    autoFillStatus: state.autoFillStatus,
    autoFillResult: state.autoFillResult,
    toggleClothing: (c) => dispatch({ type: "TOGGLE_CLOTHING", payload: c }),
    toggleColor: (c) => dispatch({ type: "TOGGLE_COLOR", payload: c }),
    setLogic: (l) => dispatch({ type: "SET_LOGIC", payload: l }),
    setThreshold: (t) => dispatch({ type: "SET_THRESHOLD", payload: t }),
    setCamera: (id) => dispatch({ type: "SET_CAMERA", payload: id }),
    setVideo: (id) => dispatch({ type: "SET_VIDEO", payload: id }),
    setTimeRange: (s, e) => {
      dispatch({ type: "SET_START_TIME", payload: s });
      dispatch({ type: "SET_END_TIME", payload: e });
    },
    setTemperature: (t) => dispatch({ type: "SET_TEMPERATURE", payload: t }),
    setBrightness: (b) => dispatch({ type: "SET_BRIGHTNESS", payload: b }),
    setVibrancy: (v) => dispatch({ type: "SET_VIBRANCY", payload: v }),
    toggleClothingGroup: (g) => dispatch({ type: "TOGGLE_CLOTHING_GROUP", payload: g }),
    resetFilters: () => dispatch({ type: "RESET_FILTERS" }),
    runSearch: state.advancedMode ? runAdvancedSearch : runSearch,
    loadMore,
    submitAutoFill,
    clearAutoFill: () => dispatch({ type: "CLEAR_AUTOFILL" }),
    openTrace: (result) => dispatch({ type: "OPEN_TRACE", payload: result }),
    closeTrace: () => dispatch({ type: "CLOSE_TRACE" }),
    openImage: (result) => dispatch({ type: "OPEN_IMAGE", payload: result }),
    closeImage: () => dispatch({ type: "CLOSE_IMAGE" }),
    setDetectionDetail: (detail) => dispatch({ type: "SET_DETECTION_DETAIL", payload: detail }),
    // Advanced search helpers
    openAdvancedModal: () => dispatch({ type: "OPEN_ADVANCED_MODAL" }),
    closeAdvancedModal: () => dispatch({ type: "CLOSE_ADVANCED_MODAL" }),
    addAdvancedFilter: (filter) => dispatch({ type: "ADD_ADVANCED_FILTER", payload: filter }),
    removeAdvancedFilter: (clothing) => dispatch({ type: "REMOVE_ADVANCED_FILTER", payload: clothing }),
    updateAdvancedFilter: (filter) => dispatch({ type: "UPDATE_ADVANCED_FILTER", payload: filter }),
    setGlobalClothingLogic: (logic) => dispatch({ type: "SET_GLOBAL_CLOTHING_LOGIC", payload: logic }),
    clearAdvancedFilters: () => dispatch({ type: "CLEAR_ADVANCED_FILTERS" }),
    applyAdvancedSearch: () => {
      dispatch({ type: "APPLY_ADVANCED_SEARCH" });
    },
    runAdvancedSearch,
  };

  return (
    <InvestigationContext.Provider value={value}>
      {children}
    </InvestigationContext.Provider>
  );
}