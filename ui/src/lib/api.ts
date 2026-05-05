/**
 * api.ts — Shared FastAPI base URL
 *
 * ใช้ไฟล์นี้เป็นจุดเดียวสำหรับ base URL ของ FastAPI backend
 * เพื่อให้แก้ไข URL ได้ที่ .env.local ที่เดียว
 *
 * Usage:
 *   import { API } from "@/lib/api";
 *   const res = await fetch(`${API}/api/cameras`);
 */

// NEXT_PUBLIC_API_URL มาจาก .env.local — ถูก bundle เข้า browser อัตโนมัติ
export const API =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
