import { motion, AnimatePresence } from 'framer-motion';
import { useTsfStore } from '@/store/useTsfStore';
import { DailyReportPanel } from './DailyReportPanel';
import { X } from 'lucide-react';

export function ReportModal() {
  const isReportModalOpen = useTsfStore((s) => s.isReportModalOpen);
  const closeReportModal = useTsfStore((s) => s.closeReportModal);

  return (
    <AnimatePresence>
      {isReportModalOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3 }}
          className="pointer-events-auto fixed inset-0 z-50 flex items-center justify-center"
          style={{ backgroundColor: 'rgba(5, 8, 15, 0.92)', backdropFilter: 'blur(12px)' }}
          onClick={closeReportModal}
        >
          <motion.div
            initial={{ scale: 0.92, opacity: 0, y: 16 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.92, opacity: 0, y: 16 }}
            transition={{ type: 'spring', stiffness: 300, damping: 28 }}
            className="relative max-h-[85vh] w-full max-w-md overflow-y-auto rounded-xl border border-[#1e293b] bg-[#0f172a]/95 p-5 shadow-2xl backdrop-blur-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={closeReportModal}
              className="absolute right-3 top-3 flex h-7 w-7 items-center justify-center rounded-full bg-[#1e293b] text-[#475569] transition-all hover:bg-[#334155] hover:text-[#e2e8f0]"
            >
              <X className="h-3.5 w-3.5" />
            </button>
            <div className="mb-3">
              <h2 className="text-lg font-bold tracking-wider text-[#e2e8f0]">DAILY REPORT</h2>
              <p className="text-[10px] text-[#475569]">End of day — review before continuing</p>
            </div>
            <DailyReportPanel />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
