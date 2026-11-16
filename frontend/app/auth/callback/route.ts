import type { NextRequest } from "next/server";

import { handleEmailCallback } from "@/features/auth/email-callback";

export function GET(request: NextRequest) {
  return handleEmailCallback(request, "code");
}
