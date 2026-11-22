
%struct.GCThread = type { i64, i64, i64, i64, [8192 x i64] }
%struct.timespec = type { i64, i64 }

@__threadon_gc_alloc.env_initialized = internal unnamed_addr global i1 false, align 4
@__gc_str = private unnamed_addr constant [22 x i8] c"THREADON_GC_THRESHOLD\00", align 1
@gc_disabled = internal unnamed_addr global i1 false, align 4
@gc_threshold = internal unnamed_addr global i64 4194304, align 8
@__gc_str_1 = private unnamed_addr constant [18 x i8] c"THREADON_GC_STATS\00", align 1
@gc_stats = internal unnamed_addr global i1 false, align 4
@gc_collecting = internal unnamed_addr global i64 0, align 8
@gc_bytes = internal unnamed_addr global i64 0, align 8
@gc_epoch = internal global i64 1, align 8
@gc_snap_gen = internal global i64 0, align 8
@gc_head = internal unnamed_addr global i64 0, align 8
@gc_min = internal unnamed_addr global i64 -1, align 8
@gc_max = internal unnamed_addr global i64 0, align 8
@gc_my_id = internal thread_local unnamed_addr global i64 0, align 8
@gc_root_count = internal unnamed_addr global i64 0, align 8
@gc_roots = internal unnamed_addr global [512 x i64] zeroinitializer, align 16
@gc_thread_count = internal unnamed_addr global i64 0, align 8
@gc_threads = internal unnamed_addr global [128 x %struct.GCThread] zeroinitializer, align 16
@__gc_str_3 = private unnamed_addr constant [134 x i8] c"[gc] collections=%llu snapshots=%llu snapshot_max=%.0fus snapshot_avg=%.0fus mark_max=%.0fus sweep_max=%.0fus collector_total=%.1fms\0A\00", align 1
@gc_collections = internal global i64 0, align 8
@gc_snapshot_count = internal global i64 0, align 8
@gc_max_snapshot_ns = internal global i64 0, align 8
@gc_sum_snapshot_ns = internal global i64 0, align 8
@gc_max_mark_ns = internal global i64 0, align 8
@gc_max_sweep_ns = internal global i64 0, align 8
@gc_sum_collector_ns = internal global i64 0, align 8
@gc_lock = internal global i8 0, align 1

; Function Attrs: nounwind uwtable
define dso_local nonnull ptr @__threadon_gc_alloc(i64 noundef %0, i64 noundef %1) local_unnamed_addr #0 {
  %3 = alloca %struct.timespec, align 8
  %4 = alloca %struct.timespec, align 8
  %5 = alloca i64, align 8
  %6 = load i1, ptr @__threadon_gc_alloc.env_initialized, align 4
  br i1 %6, label %32, label %7

7:                                                ; preds = %2
  %8 = tail call ptr @getenv(ptr noundef nonnull @__gc_str) #14
  %9 = icmp eq ptr %8, null
  br i1 %9, label %15, label %10

10:                                               ; preds = %7
  %11 = tail call i64 @strtoull(ptr nocapture noundef nonnull %8, ptr noundef null, i32 noundef 0) #14
  %12 = icmp eq i64 %11, 0
  br i1 %12, label %13, label %14

13:                                               ; preds = %10
  store i1 true, ptr @gc_disabled, align 4
  br label %15

14:                                               ; preds = %10
  store i64 %11, ptr @gc_threshold, align 8, !tbaa !5
  br label %15

15:                                               ; preds = %13, %14, %7
  %16 = tail call ptr @getenv(ptr noundef nonnull @__gc_str_1) #14
  %17 = icmp eq ptr %16, null
  br i1 %17, label %31, label %18

18:                                               ; preds = %15
  %19 = load i8, ptr %16, align 1
  %20 = zext i8 %19 to i32
  %21 = add nsw i32 %20, -48
  %22 = icmp eq i32 %21, 0
  br i1 %22, label %23, label %27

23:                                               ; preds = %18
  %24 = getelementptr inbounds i8, ptr %16, i64 1
  %25 = load i8, ptr %24, align 1
  %26 = zext i8 %25 to i32
  br label %27

27:                                               ; preds = %18, %23
  %28 = phi i32 [ %21, %18 ], [ %26, %23 ]
  %29 = icmp eq i32 %28, 0
  br i1 %29, label %31, label %30

30:                                               ; preds = %27
  store i1 true, ptr @gc_stats, align 4
  br label %31

31:                                               ; preds = %30, %27, %15
  store i1 true, ptr @__threadon_gc_alloc.env_initialized, align 4
  br label %32

32:                                               ; preds = %31, %2
  %33 = add i64 %0, 55
  %34 = and i64 %33, -8
  %35 = icmp ult i64 %33, 48
  %36 = select i1 %35, i64 48, i64 %34
  %37 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %38 = icmp eq i8 %37, 0
  br i1 %38, label %43, label %39

39:                                               ; preds = %32, %39
  %40 = tail call i32 @sched_yield() #14
  %41 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %42 = icmp eq i8 %41, 0
  br i1 %42, label %43, label %39, !llvm.loop !9

43:                                               ; preds = %39, %32
  %44 = load atomic i64, ptr @gc_collecting seq_cst, align 8
  %45 = load i1, ptr @gc_disabled, align 4
  %46 = icmp ne i64 %44, 0
  %47 = select i1 %45, i1 true, i1 %46
  br i1 %47, label %55, label %48

48:                                               ; preds = %43
  %49 = load i64, ptr @gc_bytes, align 8, !tbaa !5
  %50 = load i64, ptr @gc_threshold, align 8, !tbaa !5
  %51 = icmp ugt i64 %49, %50
  br i1 %51, label %52, label %55

52:                                               ; preds = %48
  store atomic i64 1, ptr @gc_collecting seq_cst, align 8
  %53 = atomicrmw add ptr @gc_epoch, i64 1 seq_cst, align 8
  %54 = atomicrmw add ptr @gc_snap_gen, i64 1 seq_cst, align 8
  br label %55

55:                                               ; preds = %52, %48, %43
  %56 = phi i1 [ true, %43 ], [ false, %52 ], [ true, %48 ]
  %57 = tail call noalias ptr @malloc(i64 noundef %36) #15
  %58 = icmp eq ptr %57, null
  br i1 %58, label %59, label %60

59:                                               ; preds = %55
  tail call void @abort() #16
  unreachable

60:                                               ; preds = %55
  store i64 6073194554910330702, ptr %57, align 8, !tbaa !11
  %61 = getelementptr inbounds i8, ptr %57, i64 8
  store i64 %36, ptr %61, align 8, !tbaa !13
  %62 = getelementptr inbounds i8, ptr %57, i64 32
  tail call void @llvm.memset.p0.i64(ptr noundef nonnull align 8 dereferenceable(16) %62, i8 0, i64 16, i1 false)
  %63 = load atomic i64, ptr @gc_collecting seq_cst, align 8
  %64 = icmp eq i64 %63, 0
  br i1 %64, label %67, label %65

65:                                               ; preds = %60
  %66 = load atomic i64, ptr @gc_epoch seq_cst, align 8
  br label %67

67:                                               ; preds = %60, %65
  %68 = phi i64 [ %66, %65 ], [ 0, %60 ]
  %69 = getelementptr inbounds i8, ptr %57, i64 16
  store i64 %68, ptr %69, align 8, !tbaa !14
  %70 = load i64, ptr @gc_head, align 8, !tbaa !5
  %71 = getelementptr inbounds i8, ptr %57, i64 24
  store i64 %70, ptr %71, align 8, !tbaa !15
  %72 = ptrtoint ptr %57 to i64
  store i64 %72, ptr @gc_head, align 8, !tbaa !5
  %73 = load i64, ptr @gc_bytes, align 8, !tbaa !5
  %74 = add i64 %73, %36
  store i64 %74, ptr @gc_bytes, align 8, !tbaa !5
  %75 = load i64, ptr @gc_min, align 8, !tbaa !5
  %76 = icmp ugt i64 %75, %72
  br i1 %76, label %77, label %78

77:                                               ; preds = %67
  store i64 %72, ptr @gc_min, align 8, !tbaa !5
  br label %78

78:                                               ; preds = %77, %67
  %79 = add i64 %36, %72
  %80 = load i64, ptr @gc_max, align 8, !tbaa !5
  %81 = icmp ugt i64 %79, %80
  br i1 %81, label %82, label %83

82:                                               ; preds = %78
  store i64 %79, ptr @gc_max, align 8, !tbaa !5
  br label %83

83:                                               ; preds = %82, %78
  store atomic volatile i8 0, ptr @gc_lock release, align 1
  %84 = tail call align 8 ptr @llvm.threadlocal.address.p0(ptr align 8 @gc_my_id)
  %85 = load i64, ptr %84, align 8, !tbaa !5
  %86 = icmp eq i64 %85, 0
  br i1 %86, label %186, label %87

87:                                               ; preds = %83
  %88 = load atomic i64, ptr @gc_collecting seq_cst, align 8
  %89 = icmp eq i64 %88, 0
  br i1 %89, label %186, label %90

90:                                               ; preds = %87
  %91 = load i64, ptr %84, align 8, !tbaa !5
  %92 = add i64 %91, -129
  %93 = icmp ult i64 %92, -128
  br i1 %93, label %186, label %94

94:                                               ; preds = %90
  %95 = add nsw i64 %91, -1
  %96 = getelementptr inbounds [128 x %struct.GCThread], ptr @gc_threads, i64 0, i64 %95
  %97 = load atomic i64, ptr @gc_snap_gen seq_cst, align 8
  %98 = getelementptr inbounds i8, ptr %96, i64 16
  %99 = load i64, ptr %98, align 16, !tbaa !16
  %100 = icmp eq i64 %99, %97
  br i1 %100, label %186, label %101

101:                                              ; preds = %94
  %102 = tail call ptr @llvm.frameaddress.p0(i32 0)
  %103 = ptrtoint ptr %102 to i64
  %104 = getelementptr inbounds i8, ptr %96, i64 8
  %105 = load i64, ptr %104, align 8, !tbaa !18
  %106 = icmp ne i64 %105, 0
  %107 = icmp ugt i64 %105, %103
  %108 = select i1 %106, i1 %107, i1 false
  br i1 %108, label %109, label %186

109:                                              ; preds = %101
  %110 = load i1, ptr @gc_stats, align 4
  br i1 %110, label %111, label %118

111:                                              ; preds = %109
  call void @llvm.lifetime.start.p0(i64 16, ptr nonnull %4) #17
  %112 = call i32 @clock_gettime(i32 noundef 1, ptr noundef nonnull %4) #14
  %113 = load i64, ptr %4, align 8, !tbaa !19
  %114 = mul i64 %113, -1000000000
  %115 = getelementptr inbounds i8, ptr %4, i64 8
  %116 = load i64, ptr %115, align 8, !tbaa !21
  %117 = sub i64 %114, %116
  call void @llvm.lifetime.end.p0(i64 16, ptr nonnull %4) #17
  br label %118

118:                                              ; preds = %111, %109
  %119 = phi i64 [ %117, %111 ], [ 0, %109 ]
  %120 = add i64 %103, 8
  %121 = icmp ugt i64 %120, %105
  br i1 %121, label %126, label %122

122:                                              ; preds = %118
  %123 = load i64, ptr @gc_min, align 8
  %124 = load i64, ptr @gc_max, align 8
  %125 = getelementptr inbounds i8, ptr %96, i64 32
  br label %130

126:                                              ; preds = %162, %118
  %127 = phi i64 [ 0, %118 ], [ %163, %162 ]
  %128 = getelementptr inbounds i8, ptr %96, i64 24
  store i64 %127, ptr %128, align 8, !tbaa !22
  store atomic i64 %97, ptr %98 seq_cst, align 16
  %129 = load i1, ptr @gc_stats, align 4
  br i1 %129, label %168, label %186

130:                                              ; preds = %162, %122
  %131 = phi i64 [ %120, %122 ], [ %164, %162 ]
  %132 = phi i64 [ 0, %122 ], [ %163, %162 ]
  %133 = phi ptr [ %102, %122 ], [ %134, %162 ]
  %134 = inttoptr i64 %131 to ptr
  %135 = load volatile i64, ptr %133, align 8, !tbaa !5
  %136 = and i64 %135, -2
  %137 = icmp eq i64 %136, 0
  %138 = and i64 %135, 6
  %139 = icmp ne i64 %138, 0
  %140 = or i1 %137, %139
  %141 = icmp ult i64 %136, %123
  %142 = select i1 %140, i1 true, i1 %141
  br i1 %142, label %162, label %143

143:                                              ; preds = %130
  %144 = icmp ugt i64 %136, %124
  %145 = icmp ult i64 %135, 48
  %146 = or i1 %145, %144
  br i1 %146, label %162, label %147

147:                                              ; preds = %143
  %148 = add i64 %136, -48
  %149 = inttoptr i64 %148 to ptr
  %150 = load i64, ptr %149, align 8, !tbaa !11
  %151 = icmp eq i64 %150, 6073194554910330702
  br i1 %151, label %152, label %162

152:                                              ; preds = %147
  %153 = getelementptr inbounds i8, ptr %149, i64 8
  %154 = load i64, ptr %153, align 8, !tbaa !13
  %155 = icmp ult i64 %154, 48
  %156 = add i64 %154, %148
  %157 = icmp ult i64 %156, %136
  %158 = or i1 %155, %157
  br i1 %158, label %162, label %159

159:                                              ; preds = %152
  %160 = add nuw nsw i64 %132, 1
  %161 = getelementptr inbounds [8192 x i64], ptr %125, i64 0, i64 %132
  store i64 %136, ptr %161, align 8, !tbaa !5
  br label %162

162:                                              ; preds = %159, %152, %147, %143, %130
  %163 = phi i64 [ %160, %159 ], [ %132, %130 ], [ %132, %143 ], [ %132, %147 ], [ %132, %152 ]
  %164 = add i64 %131, 8
  %165 = icmp ule i64 %164, %105
  %166 = icmp ult i64 %163, 8192
  %167 = select i1 %165, i1 %166, i1 false
  br i1 %167, label %130, label %126, !llvm.loop !23

168:                                              ; preds = %126
  call void @llvm.lifetime.start.p0(i64 16, ptr nonnull %3) #17
  %169 = call i32 @clock_gettime(i32 noundef 1, ptr noundef nonnull %3) #14
  %170 = load i64, ptr %3, align 8, !tbaa !19
  %171 = mul i64 %170, 1000000000
  %172 = getelementptr inbounds i8, ptr %3, i64 8
  %173 = load i64, ptr %172, align 8, !tbaa !21
  call void @llvm.lifetime.end.p0(i64 16, ptr nonnull %3) #17
  %174 = add i64 %173, %119
  %175 = add i64 %174, %171
  %176 = atomicrmw add ptr @gc_sum_snapshot_ns, i64 %175 monotonic, align 8
  %177 = atomicrmw add ptr @gc_snapshot_count, i64 1 monotonic, align 8
  %178 = load atomic i64, ptr @gc_max_snapshot_ns monotonic, align 8
  br label %179

179:                                              ; preds = %182, %168
  %180 = phi i64 [ %178, %168 ], [ %185, %182 ]
  %181 = icmp ugt i64 %175, %180
  br i1 %181, label %182, label %186

182:                                              ; preds = %179
  %183 = cmpxchg ptr @gc_max_snapshot_ns, i64 %180, i64 %175 monotonic monotonic, align 8
  %184 = extractvalue { i64, i1 } %183, 1
  %185 = extractvalue { i64, i1 } %183, 0
  br i1 %184, label %186, label %179, !llvm.loop !24

186:                                              ; preds = %182, %179, %126, %101, %94, %90, %87, %83
  br i1 %56, label %195, label %187

187:                                              ; preds = %186
  call void @llvm.lifetime.start.p0(i64 8, ptr nonnull %5) #17
  %188 = call i32 @pthread_create(ptr noundef nonnull %5, ptr noundef null, ptr noundef nonnull @gc_collector_main, ptr noundef null) #14
  %189 = icmp eq i32 %188, 0
  br i1 %189, label %190, label %193

190:                                              ; preds = %187
  %191 = load i64, ptr %5, align 8, !tbaa !5
  %192 = call i32 @pthread_detach(i64 noundef %191) #14
  br label %194

193:                                              ; preds = %187
  store atomic i64 0, ptr @gc_collecting seq_cst, align 8
  br label %194

194:                                              ; preds = %193, %190
  call void @llvm.lifetime.end.p0(i64 8, ptr nonnull %5) #17
  br label %195

195:                                              ; preds = %194, %186
  %196 = getelementptr inbounds i8, ptr %57, i64 48
  ret ptr %196
}

; Function Attrs: mustprogress nocallback nofree nosync nounwind willreturn memory(argmem: readwrite)
declare void @llvm.lifetime.start.p0(i64 immarg, ptr nocapture) #1

; Function Attrs: nofree nounwind memory(read)
declare noundef ptr @getenv(ptr nocapture noundef) local_unnamed_addr #2

; Function Attrs: mustprogress nofree nounwind willreturn
declare i64 @strtoull(ptr noundef readonly, ptr nocapture noundef, i32 noundef) local_unnamed_addr #3

; Function Attrs: mustprogress nocallback nofree nosync nounwind willreturn memory(argmem: readwrite)
declare void @llvm.lifetime.end.p0(i64 immarg, ptr nocapture) #1

; Function Attrs: nounwind
declare noalias ptr @malloc(i64 noundef) local_unnamed_addr #4

; Function Attrs: cold noreturn nounwind
declare void @abort() local_unnamed_addr #5

; Function Attrs: mustprogress nocallback nofree nosync nounwind speculatable willreturn memory(none)
declare nonnull ptr @llvm.threadlocal.address.p0(ptr nonnull) #6

; Function Attrs: nounwind
declare i32 @pthread_create(ptr noundef, ptr noundef, ptr noundef, ptr noundef) local_unnamed_addr #4

; Function Attrs: nounwind uwtable
define internal noalias noundef ptr @gc_collector_main(ptr nocapture readnone %0) #0 {
  %2 = alloca %struct.timespec, align 8
  %3 = alloca %struct.timespec, align 8
  %4 = alloca %struct.timespec, align 8
  %5 = alloca %struct.timespec, align 8
  %6 = alloca %struct.timespec, align 8
  %7 = alloca %struct.timespec, align 8
  %8 = alloca %struct.timespec, align 8
  %9 = alloca %struct.timespec, align 8
  %10 = load i1, ptr @gc_stats, align 4
  br i1 %10, label %11, label %18

11:                                               ; preds = %1
  call void @llvm.lifetime.start.p0(i64 16, ptr nonnull %9) #17
  %12 = call i32 @clock_gettime(i32 noundef 1, ptr noundef nonnull %9) #14
  %13 = load i64, ptr %9, align 8, !tbaa !19
  %14 = mul i64 %13, -1000000000
  %15 = getelementptr inbounds i8, ptr %9, i64 8
  %16 = load i64, ptr %15, align 8, !tbaa !21
  %17 = sub i64 %14, %16
  call void @llvm.lifetime.end.p0(i64 16, ptr nonnull %9) #17
  br label %18

18:                                               ; preds = %1, %11
  %19 = phi i64 [ %17, %11 ], [ 0, %1 ]
  %20 = atomicrmw add ptr @gc_collections, i64 1 monotonic, align 8
  %21 = load atomic i64, ptr @gc_snap_gen seq_cst, align 8
  call void @llvm.lifetime.start.p0(i64 16, ptr nonnull %8) #17
  store i64 0, ptr %8, align 8, !tbaa !19
  %22 = getelementptr inbounds i8, ptr %8, i64 8
  store i64 1000000, ptr %22, align 8, !tbaa !21
  br label %23

23:                                               ; preds = %46, %18
  %24 = phi i32 [ 0, %18 ], [ %48, %46 ]
  %25 = load i64, ptr @gc_thread_count, align 8, !tbaa !5
  %26 = icmp eq i64 %25, 0
  br i1 %26, label %50, label %27

27:                                               ; preds = %23, %40
  %28 = phi i64 [ %41, %40 ], [ %25, %23 ]
  %29 = phi i64 [ %42, %40 ], [ 0, %23 ]
  %30 = getelementptr inbounds [128 x %struct.GCThread], ptr @gc_threads, i64 0, i64 %29
  %31 = getelementptr inbounds i8, ptr %30, i64 8
  %32 = load i64, ptr %31, align 8, !tbaa !18
  %33 = icmp eq i64 %32, 0
  br i1 %33, label %40, label %34

34:                                               ; preds = %27
  %35 = getelementptr inbounds i8, ptr %30, i64 16
  %36 = load atomic i64, ptr %35 seq_cst, align 16
  %37 = icmp ult i64 %36, %21
  br i1 %37, label %46, label %38

38:                                               ; preds = %34
  %39 = load i64, ptr @gc_thread_count, align 8, !tbaa !5
  br label %40

40:                                               ; preds = %38, %27
  %41 = phi i64 [ %39, %38 ], [ %28, %27 ]
  %42 = add nuw nsw i64 %29, 1
  %43 = icmp ult i64 %42, %41
  %44 = icmp ult i64 %29, 127
  %45 = and i1 %44, %43
  br i1 %45, label %27, label %50, !llvm.loop !25

46:                                               ; preds = %34
  %47 = call i32 @nanosleep(ptr noundef nonnull %8, ptr noundef null) #14
  %48 = add nuw nsw i32 %24, 1
  %49 = icmp eq i32 %48, 8
  br i1 %49, label %50, label %23, !llvm.loop !26

50:                                               ; preds = %23, %46, %40
  call void @llvm.lifetime.end.p0(i64 16, ptr nonnull %8) #17
  %51 = load i1, ptr @gc_stats, align 4
  br i1 %51, label %52, label %59

52:                                               ; preds = %50
  call void @llvm.lifetime.start.p0(i64 16, ptr nonnull %7) #17
  %53 = call i32 @clock_gettime(i32 noundef 1, ptr noundef nonnull %7) #14
  %54 = load i64, ptr %7, align 8, !tbaa !19
  %55 = mul i64 %54, -1000000000
  %56 = getelementptr inbounds i8, ptr %7, i64 8
  %57 = load i64, ptr %56, align 8, !tbaa !21
  %58 = sub i64 %55, %57
  call void @llvm.lifetime.end.p0(i64 16, ptr nonnull %7) #17
  br label %59

59:                                               ; preds = %50, %52
  %60 = phi i64 [ %58, %52 ], [ 0, %50 ]
  call fastcc void @gc_mark_roots() #18
  %61 = atomicrmw add ptr @gc_snap_gen, i64 1 seq_cst, align 8
  %62 = load atomic i64, ptr @gc_snap_gen seq_cst, align 8
  call void @llvm.lifetime.start.p0(i64 16, ptr nonnull %6) #17
  store i64 0, ptr %6, align 8, !tbaa !19
  %63 = getelementptr inbounds i8, ptr %6, i64 8
  store i64 1000000, ptr %63, align 8, !tbaa !21
  br label %64

64:                                               ; preds = %87, %59
  %65 = phi i32 [ 0, %59 ], [ %89, %87 ]
  %66 = load i64, ptr @gc_thread_count, align 8, !tbaa !5
  %67 = icmp eq i64 %66, 0
  br i1 %67, label %91, label %68

68:                                               ; preds = %64, %81
  %69 = phi i64 [ %82, %81 ], [ %66, %64 ]
  %70 = phi i64 [ %83, %81 ], [ 0, %64 ]
  %71 = getelementptr inbounds [128 x %struct.GCThread], ptr @gc_threads, i64 0, i64 %70
  %72 = getelementptr inbounds i8, ptr %71, i64 8
  %73 = load i64, ptr %72, align 8, !tbaa !18
  %74 = icmp eq i64 %73, 0
  br i1 %74, label %81, label %75

75:                                               ; preds = %68
  %76 = getelementptr inbounds i8, ptr %71, i64 16
  %77 = load atomic i64, ptr %76 seq_cst, align 16
  %78 = icmp ult i64 %77, %62
  br i1 %78, label %87, label %79

79:                                               ; preds = %75
  %80 = load i64, ptr @gc_thread_count, align 8, !tbaa !5
  br label %81

81:                                               ; preds = %79, %68
  %82 = phi i64 [ %80, %79 ], [ %69, %68 ]
  %83 = add nuw nsw i64 %70, 1
  %84 = icmp ult i64 %83, %82
  %85 = icmp ult i64 %70, 127
  %86 = and i1 %85, %84
  br i1 %86, label %68, label %91, !llvm.loop !25

87:                                               ; preds = %75
  %88 = call i32 @nanosleep(ptr noundef nonnull %6, ptr noundef null) #14
  %89 = add nuw nsw i32 %65, 1
  %90 = icmp eq i32 %89, 8
  br i1 %90, label %91, label %64, !llvm.loop !26

91:                                               ; preds = %64, %87, %81
  call void @llvm.lifetime.end.p0(i64 16, ptr nonnull %6) #17
  call fastcc void @gc_mark_roots() #18
  %92 = load i1, ptr @gc_stats, align 4
  br i1 %92, label %93, label %118

93:                                               ; preds = %91
  call void @llvm.lifetime.start.p0(i64 16, ptr nonnull %5) #17
  %94 = call i32 @clock_gettime(i32 noundef 1, ptr noundef nonnull %5) #14
  %95 = load i64, ptr %5, align 8, !tbaa !19
  %96 = mul i64 %95, 1000000000
  %97 = getelementptr inbounds i8, ptr %5, i64 8
  %98 = load i64, ptr %97, align 8, !tbaa !21
  call void @llvm.lifetime.end.p0(i64 16, ptr nonnull %5) #17
  %99 = add i64 %98, %60
  %100 = add i64 %99, %96
  %101 = load atomic i64, ptr @gc_max_mark_ns monotonic, align 8
  br label %102

102:                                              ; preds = %105, %93
  %103 = phi i64 [ %101, %93 ], [ %108, %105 ]
  %104 = icmp ugt i64 %100, %103
  br i1 %104, label %105, label %109

105:                                              ; preds = %102
  %106 = cmpxchg ptr @gc_max_mark_ns, i64 %103, i64 %100 monotonic monotonic, align 8
  %107 = extractvalue { i64, i1 } %106, 1
  %108 = extractvalue { i64, i1 } %106, 0
  br i1 %107, label %109, label %102, !llvm.loop !27

109:                                              ; preds = %105, %102
  %110 = load i1, ptr @gc_stats, align 4
  br i1 %110, label %111, label %118

111:                                              ; preds = %109
  call void @llvm.lifetime.start.p0(i64 16, ptr nonnull %4) #17
  %112 = call i32 @clock_gettime(i32 noundef 1, ptr noundef nonnull %4) #14
  %113 = load i64, ptr %4, align 8, !tbaa !19
  %114 = mul i64 %113, -1000000000
  %115 = getelementptr inbounds i8, ptr %4, i64 8
  %116 = load i64, ptr %115, align 8, !tbaa !21
  %117 = sub i64 %114, %116
  call void @llvm.lifetime.end.p0(i64 16, ptr nonnull %4) #17
  br label %118

118:                                              ; preds = %91, %109, %111
  %119 = phi i64 [ %117, %111 ], [ 0, %109 ], [ 0, %91 ]
  %120 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %121 = icmp eq i8 %120, 0
  br i1 %121, label %126, label %122

122:                                              ; preds = %118, %122
  %123 = call i32 @sched_yield() #14
  %124 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %125 = icmp eq i8 %124, 0
  br i1 %125, label %126, label %122, !llvm.loop !9

126:                                              ; preds = %122, %118
  %127 = load atomic i64, ptr @gc_epoch seq_cst, align 8
  %128 = load i64, ptr @gc_head, align 8, !tbaa !5
  %129 = icmp eq i64 %128, 0
  br i1 %129, label %147, label %130

130:                                              ; preds = %126, %144
  %131 = phi ptr [ %145, %144 ], [ @gc_head, %126 ]
  %132 = phi i64 [ %135, %144 ], [ %128, %126 ]
  %133 = inttoptr i64 %132 to ptr
  %134 = getelementptr inbounds i8, ptr %133, i64 24
  %135 = load i64, ptr %134, align 8, !tbaa !15
  %136 = getelementptr inbounds i8, ptr %133, i64 16
  %137 = load atomic i64, ptr %136 seq_cst, align 8
  %138 = icmp eq i64 %137, %127
  br i1 %138, label %144, label %139

139:                                              ; preds = %130
  store i64 %135, ptr %131, align 8, !tbaa !5
  %140 = getelementptr inbounds i8, ptr %133, i64 8
  %141 = load i64, ptr %140, align 8, !tbaa !13
  %142 = load i64, ptr @gc_bytes, align 8, !tbaa !5
  %143 = sub i64 %142, %141
  store i64 %143, ptr @gc_bytes, align 8, !tbaa !5
  call void @free(ptr noundef nonnull %133) #15
  br label %144

144:                                              ; preds = %139, %130
  %145 = phi ptr [ %131, %139 ], [ %134, %130 ]
  %146 = icmp eq i64 %135, 0
  br i1 %146, label %147, label %130, !llvm.loop !28

147:                                              ; preds = %144, %126
  store atomic volatile i8 0, ptr @gc_lock release, align 1
  %148 = load i1, ptr @gc_stats, align 4
  br i1 %148, label %149, label %174

149:                                              ; preds = %147
  call void @llvm.lifetime.start.p0(i64 16, ptr nonnull %3) #17
  %150 = call i32 @clock_gettime(i32 noundef 1, ptr noundef nonnull %3) #14
  %151 = load i64, ptr %3, align 8, !tbaa !19
  %152 = mul i64 %151, 1000000000
  %153 = getelementptr inbounds i8, ptr %3, i64 8
  %154 = load i64, ptr %153, align 8, !tbaa !21
  call void @llvm.lifetime.end.p0(i64 16, ptr nonnull %3) #17
  %155 = add i64 %154, %119
  %156 = add i64 %155, %152
  %157 = load atomic i64, ptr @gc_max_sweep_ns monotonic, align 8
  br label %158

158:                                              ; preds = %161, %149
  %159 = phi i64 [ %157, %149 ], [ %164, %161 ]
  %160 = icmp ugt i64 %156, %159
  br i1 %160, label %161, label %165

161:                                              ; preds = %158
  %162 = cmpxchg ptr @gc_max_sweep_ns, i64 %159, i64 %156 monotonic monotonic, align 8
  %163 = extractvalue { i64, i1 } %162, 1
  %164 = extractvalue { i64, i1 } %162, 0
  br i1 %163, label %165, label %158, !llvm.loop !29

165:                                              ; preds = %158, %161
  call void @llvm.lifetime.start.p0(i64 16, ptr nonnull %2) #17
  %166 = call i32 @clock_gettime(i32 noundef 1, ptr noundef nonnull %2) #14
  %167 = load i64, ptr %2, align 8, !tbaa !19
  %168 = mul i64 %167, 1000000000
  %169 = getelementptr inbounds i8, ptr %2, i64 8
  %170 = load i64, ptr %169, align 8, !tbaa !21
  call void @llvm.lifetime.end.p0(i64 16, ptr nonnull %2) #17
  %171 = add i64 %170, %19
  %172 = add i64 %171, %168
  %173 = atomicrmw add ptr @gc_sum_collector_ns, i64 %172 monotonic, align 8
  br label %174

174:                                              ; preds = %165, %147
  store atomic i64 0, ptr @gc_collecting seq_cst, align 8
  ret ptr null
}

; Function Attrs: nounwind
declare i32 @pthread_detach(i64 noundef) local_unnamed_addr #4

; Function Attrs: nounwind uwtable
define dso_local void @__threadon_gc_barrier(i64 noundef %0, i64 noundef %1) local_unnamed_addr #0 {
  %3 = load atomic i64, ptr @gc_collecting seq_cst, align 8
  %4 = icmp eq i64 %3, 0
  %5 = icmp ult i64 %1, 8
  %6 = or i1 %4, %5
  br i1 %6, label %148, label %7

7:                                                ; preds = %2, %145
  %8 = phi i64 [ %146, %145 ], [ 8, %2 ]
  %9 = phi i64 [ %8, %145 ], [ 0, %2 ]
  %10 = add i64 %9, %0
  %11 = inttoptr i64 %10 to ptr
  %12 = load volatile i64, ptr %11, align 8, !tbaa !5
  %13 = and i64 %12, -2
  %14 = icmp eq i64 %13, 0
  %15 = and i64 %12, 6
  %16 = icmp ne i64 %15, 0
  %17 = or i1 %14, %16
  %18 = load i64, ptr @gc_min, align 8
  %19 = icmp ult i64 %13, %18
  %20 = select i1 %17, i1 true, i1 %19
  br i1 %20, label %145, label %21

21:                                               ; preds = %7
  %22 = load i64, ptr @gc_max, align 8
  %23 = icmp ugt i64 %13, %22
  %24 = icmp ult i64 %12, 48
  %25 = or i1 %24, %23
  br i1 %25, label %145, label %26

26:                                               ; preds = %21
  %27 = add i64 %13, -48
  %28 = inttoptr i64 %27 to ptr
  %29 = load i64, ptr %28, align 8, !tbaa !11
  %30 = icmp eq i64 %29, 6073194554910330702
  br i1 %30, label %31, label %145

31:                                               ; preds = %26
  %32 = getelementptr inbounds i8, ptr %28, i64 8
  %33 = load i64, ptr %32, align 8, !tbaa !13
  %34 = icmp ult i64 %33, 48
  %35 = add i64 %33, %27
  %36 = icmp ult i64 %35, %13
  %37 = or i1 %34, %36
  br i1 %37, label %145, label %38

38:                                               ; preds = %31
  %39 = tail call noalias ptr @malloc(i64 noundef 2048) #15
  %40 = icmp eq ptr %39, null
  br i1 %40, label %145, label %41

41:                                               ; preds = %38
  store i64 %13, ptr %39, align 8, !tbaa !5
  br label %42

42:                                               ; preds = %139, %41
  %43 = phi i64 [ 256, %41 ], [ %142, %139 ]
  %44 = phi i64 [ 1, %41 ], [ %141, %139 ]
  %45 = phi ptr [ %39, %41 ], [ %140, %139 ]
  %46 = add i64 %44, -1
  %47 = getelementptr inbounds i64, ptr %45, i64 %46
  %48 = load i64, ptr %47, align 8, !tbaa !5
  %49 = and i64 %48, -2
  %50 = icmp eq i64 %49, 0
  %51 = and i64 %48, 6
  %52 = icmp ne i64 %51, 0
  %53 = or i1 %50, %52
  %54 = load i64, ptr @gc_min, align 8
  %55 = icmp ult i64 %49, %54
  %56 = select i1 %53, i1 true, i1 %55
  br i1 %56, label %139, label %57

57:                                               ; preds = %42
  %58 = load i64, ptr @gc_max, align 8, !tbaa !5
  %59 = icmp ugt i64 %49, %58
  %60 = icmp ult i64 %48, 48
  %61 = or i1 %60, %59
  br i1 %61, label %139, label %62

62:                                               ; preds = %57
  %63 = add i64 %49, -48
  %64 = inttoptr i64 %63 to ptr
  %65 = load i64, ptr %64, align 8, !tbaa !11
  %66 = icmp eq i64 %65, 6073194554910330702
  br i1 %66, label %67, label %139

67:                                               ; preds = %62
  %68 = getelementptr inbounds i8, ptr %64, i64 8
  %69 = load i64, ptr %68, align 8, !tbaa !13
  %70 = icmp ult i64 %69, 48
  %71 = add i64 %69, %63
  %72 = icmp ult i64 %71, %49
  %73 = or i1 %70, %72
  br i1 %73, label %139, label %74, !llvm.loop !30

74:                                               ; preds = %67
  %75 = load atomic i64, ptr @gc_epoch seq_cst, align 8
  %76 = getelementptr inbounds i8, ptr %64, i64 16
  %77 = load atomic i64, ptr %76 seq_cst, align 8
  %78 = icmp eq i64 %77, %75
  br i1 %78, label %139, label %79, !llvm.loop !30

79:                                               ; preds = %74
  store atomic i64 %75, ptr %76 seq_cst, align 8
  %80 = load i64, ptr %68, align 8, !tbaa !13
  %81 = add i64 %80, %63
  %82 = add i64 %49, 8
  %83 = icmp ugt i64 %82, %81
  br i1 %83, label %139, label %84

84:                                               ; preds = %79
  %85 = load i64, ptr @gc_min, align 8
  br label %86

86:                                               ; preds = %84, %132
  %87 = phi i64 [ %133, %132 ], [ %85, %84 ]
  %88 = phi i64 [ %137, %132 ], [ %82, %84 ]
  %89 = phi i64 [ %136, %132 ], [ %43, %84 ]
  %90 = phi i64 [ %88, %132 ], [ %49, %84 ]
  %91 = phi i64 [ %135, %132 ], [ %46, %84 ]
  %92 = phi ptr [ %134, %132 ], [ %45, %84 ]
  %93 = inttoptr i64 %90 to ptr
  %94 = load volatile i64, ptr %93, align 8, !tbaa !5
  %95 = and i64 %94, -2
  %96 = icmp eq i64 %95, 0
  %97 = and i64 %94, 6
  %98 = icmp ne i64 %97, 0
  %99 = or i1 %96, %98
  %100 = icmp ult i64 %95, %87
  %101 = select i1 %99, i1 true, i1 %100
  br i1 %101, label %132, label %102

102:                                              ; preds = %86
  %103 = load i64, ptr @gc_max, align 8, !tbaa !5
  %104 = icmp ugt i64 %95, %103
  %105 = icmp ult i64 %94, 48
  %106 = or i1 %105, %104
  br i1 %106, label %132, label %107

107:                                              ; preds = %102
  %108 = add i64 %95, -48
  %109 = inttoptr i64 %108 to ptr
  %110 = load i64, ptr %109, align 8, !tbaa !11
  %111 = icmp eq i64 %110, 6073194554910330702
  br i1 %111, label %112, label %132

112:                                              ; preds = %107
  %113 = getelementptr inbounds i8, ptr %109, i64 8
  %114 = load i64, ptr %113, align 8, !tbaa !13
  %115 = icmp ult i64 %114, 48
  %116 = add i64 %114, %108
  %117 = icmp ult i64 %116, %95
  %118 = or i1 %115, %117
  br i1 %118, label %132, label %119

119:                                              ; preds = %112
  %120 = icmp eq i64 %91, %89
  br i1 %120, label %121, label %126

121:                                              ; preds = %119
  %122 = shl i64 %89, 1
  %123 = shl i64 %89, 4
  %124 = tail call ptr @realloc(ptr noundef %92, i64 noundef %123) #19
  %125 = icmp eq ptr %124, null
  br i1 %125, label %139, label %126

126:                                              ; preds = %121, %119
  %127 = phi ptr [ %124, %121 ], [ %92, %119 ]
  %128 = phi i64 [ %122, %121 ], [ %89, %119 ]
  %129 = add i64 %91, 1
  %130 = getelementptr inbounds i64, ptr %127, i64 %91
  store i64 %95, ptr %130, align 8, !tbaa !5
  %131 = load i64, ptr @gc_min, align 8
  br label %132

132:                                              ; preds = %126, %112, %107, %102, %86
  %133 = phi i64 [ %131, %126 ], [ %87, %86 ], [ %87, %102 ], [ %87, %107 ], [ %87, %112 ]
  %134 = phi ptr [ %127, %126 ], [ %92, %86 ], [ %92, %102 ], [ %92, %107 ], [ %92, %112 ]
  %135 = phi i64 [ %129, %126 ], [ %91, %86 ], [ %91, %102 ], [ %91, %107 ], [ %91, %112 ]
  %136 = phi i64 [ %128, %126 ], [ %89, %86 ], [ %89, %102 ], [ %89, %107 ], [ %89, %112 ]
  %137 = add i64 %88, 8
  %138 = icmp ugt i64 %137, %81
  br i1 %138, label %139, label %86, !llvm.loop !31

139:                                              ; preds = %132, %121, %79, %74, %67, %62, %57, %42
  %140 = phi ptr [ %45, %74 ], [ %45, %42 ], [ %45, %57 ], [ %45, %62 ], [ %45, %67 ], [ %45, %79 ], [ %134, %132 ], [ %92, %121 ]
  %141 = phi i64 [ %46, %74 ], [ %46, %42 ], [ %46, %57 ], [ %46, %62 ], [ %46, %67 ], [ %46, %79 ], [ %135, %132 ], [ %89, %121 ]
  %142 = phi i64 [ %43, %74 ], [ %43, %42 ], [ %43, %57 ], [ %43, %62 ], [ %43, %67 ], [ %43, %79 ], [ %136, %132 ], [ %122, %121 ]
  %143 = icmp eq i64 %141, 0
  br i1 %143, label %144, label %42

144:                                              ; preds = %139
  tail call void @free(ptr noundef %140) #15
  br label %145

145:                                              ; preds = %31, %26, %21, %7, %144, %38
  %146 = add i64 %8, 8
  %147 = icmp ugt i64 %146, %1
  br i1 %147, label %148, label %7, !llvm.loop !32

148:                                              ; preds = %145, %2
  ret void
}

; Function Attrs: nounwind uwtable
define dso_local void @__threadon_gc_add_root(ptr noundef %0, i64 noundef %1) local_unnamed_addr #0 {
  %3 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %4 = icmp eq i8 %3, 0
  br i1 %4, label %9, label %5

5:                                                ; preds = %2, %5
  %6 = tail call i32 @sched_yield() #14
  %7 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %8 = icmp eq i8 %7, 0
  br i1 %8, label %9, label %5, !llvm.loop !9

9:                                                ; preds = %5, %2
  %10 = load i64, ptr @gc_root_count, align 8, !tbaa !5
  %11 = add i64 %10, 1
  %12 = icmp ult i64 %11, 512
  br i1 %12, label %13, label %18

13:                                               ; preds = %9
  %14 = ptrtoint ptr %0 to i64
  %15 = getelementptr inbounds [512 x i64], ptr @gc_roots, i64 0, i64 %10
  store i64 %14, ptr %15, align 8, !tbaa !5
  %16 = add nsw i64 %10, 2
  store i64 %16, ptr @gc_root_count, align 8, !tbaa !5
  %17 = getelementptr inbounds [512 x i64], ptr @gc_roots, i64 0, i64 %11
  store i64 %1, ptr %17, align 8, !tbaa !5
  br label %18

18:                                               ; preds = %13, %9
  store atomic volatile i8 0, ptr @gc_lock release, align 1
  ret void
}

; Function Attrs: nounwind uwtable
define dso_local void @__threadon_gc_thread_enter(ptr noundef %0) local_unnamed_addr #0 {
  %2 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %3 = icmp eq i8 %2, 0
  br i1 %3, label %8, label %4

4:                                                ; preds = %1, %4
  %5 = tail call i32 @sched_yield() #14
  %6 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %7 = icmp eq i8 %6, 0
  br i1 %7, label %8, label %4, !llvm.loop !9

8:                                                ; preds = %4, %1
  %9 = load i64, ptr @gc_thread_count, align 8, !tbaa !5
  %10 = add i64 %9, 1
  store i64 %10, ptr @gc_thread_count, align 8, !tbaa !5
  %11 = icmp ult i64 %10, 129
  br i1 %11, label %12, label %19

12:                                               ; preds = %8
  %13 = tail call align 8 ptr @llvm.threadlocal.address.p0(ptr align 8 @gc_my_id)
  store i64 %10, ptr %13, align 8, !tbaa !5
  %14 = tail call i64 @pthread_self() #20
  %15 = getelementptr inbounds [128 x %struct.GCThread], ptr @gc_threads, i64 0, i64 %9
  store i64 %14, ptr %15, align 16, !tbaa !33
  %16 = ptrtoint ptr %0 to i64
  %17 = getelementptr inbounds i8, ptr %15, i64 8
  store i64 %16, ptr %17, align 8, !tbaa !18
  %18 = getelementptr inbounds i8, ptr %15, i64 16
  tail call void @llvm.memset.p0.i64(ptr noundef nonnull align 16 dereferenceable(16) %18, i8 0, i64 16, i1 false)
  br label %19

19:                                               ; preds = %12, %8
  store atomic volatile i8 0, ptr @gc_lock release, align 1
  ret void
}

; Function Attrs: mustprogress nofree nosync nounwind willreturn memory(none)
declare i64 @pthread_self() local_unnamed_addr #7

; Function Attrs: mustprogress nofree norecurse nosync nounwind willreturn memory(readwrite, argmem: none, inaccessiblemem: none) uwtable
define dso_local void @__threadon_gc_thread_exit() local_unnamed_addr #8 {
  %1 = tail call align 8 ptr @llvm.threadlocal.address.p0(ptr align 8 @gc_my_id)
  %2 = load i64, ptr %1, align 8
  %3 = add i64 %2, -1
  %4 = icmp ult i64 %3, 128
  br i1 %4, label %5, label %7

5:                                                ; preds = %0
  %6 = getelementptr inbounds [128 x %struct.GCThread], ptr @gc_threads, i64 0, i64 %3, i32 1
  store i64 0, ptr %6, align 8, !tbaa !18
  store i64 0, ptr %1, align 8, !tbaa !5
  br label %7

7:                                                ; preds = %5, %0
  ret void
}

; Function Attrs: nounwind uwtable
define dso_local void @__threadon_gc_shutdown() local_unnamed_addr #0 {
  br label %1

1:                                                ; preds = %0, %5
  %2 = phi i32 [ 0, %0 ], [ %7, %5 ]
  %3 = load atomic i64, ptr @gc_collecting seq_cst, align 8
  %4 = icmp eq i64 %3, 0
  br i1 %4, label %9, label %5

5:                                                ; preds = %1
  %6 = tail call i32 @sched_yield() #14
  %7 = add nuw nsw i32 %2, 1
  %8 = icmp eq i32 %7, 100000
  br i1 %8, label %9, label %1, !llvm.loop !34

9:                                                ; preds = %1, %5
  %10 = load i1, ptr @gc_stats, align 4
  br i1 %10, label %11, label %36

11:                                               ; preds = %9
  %12 = load i64, ptr @gc_collections, align 8, !tbaa !5
  %13 = load i64, ptr @gc_snapshot_count, align 8, !tbaa !5
  %14 = load i64, ptr @gc_max_snapshot_ns, align 8, !tbaa !5
  %15 = uitofp i64 %14 to double
  %16 = fdiv double %15, 1.000000e+03
  %17 = icmp eq i64 %13, 0
  br i1 %17, label %24, label %18

18:                                               ; preds = %11
  %19 = load i64, ptr @gc_sum_snapshot_ns, align 8, !tbaa !5
  %20 = uitofp i64 %19 to double
  %21 = uitofp i64 %13 to double
  %22 = fdiv double %20, %21
  %23 = fdiv double %22, 1.000000e+03
  br label %24

24:                                               ; preds = %11, %18
  %25 = phi double [ %23, %18 ], [ 0.000000e+00, %11 ]
  %26 = load i64, ptr @gc_max_mark_ns, align 8, !tbaa !5
  %27 = uitofp i64 %26 to double
  %28 = fdiv double %27, 1.000000e+03
  %29 = load i64, ptr @gc_max_sweep_ns, align 8, !tbaa !5
  %30 = uitofp i64 %29 to double
  %31 = fdiv double %30, 1.000000e+03
  %32 = load i64, ptr @gc_sum_collector_ns, align 8, !tbaa !5
  %33 = uitofp i64 %32 to double
  %34 = fdiv double %33, 1.000000e+06
  %35 = tail call i32 (ptr, ...) @printf(ptr noundef nonnull dereferenceable(1) @__gc_str_3, i64 noundef %12, i64 noundef %13, double noundef %16, double noundef %25, double noundef %28, double noundef %31, double noundef %34) #18
  br label %36

36:                                               ; preds = %24, %9
  ret void
}

; Function Attrs: nounwind
declare i32 @sched_yield() local_unnamed_addr #4

; Function Attrs: nofree nounwind
declare noundef i32 @printf(ptr nocapture noundef readonly, ...) local_unnamed_addr #9

; Function Attrs: mustprogress nocallback nofree nosync nounwind willreturn memory(none)
declare ptr @llvm.frameaddress.p0(i32 immarg) #10

; Function Attrs: nounwind
declare i32 @clock_gettime(i32 noundef, ptr noundef) local_unnamed_addr #4

; Function Attrs: nounwind uwtable
define internal fastcc void @gc_mark_roots() unnamed_addr #0 {
  %1 = tail call noalias ptr @malloc(i64 noundef 2048) #15
  %2 = icmp eq ptr %1, null
  br i1 %2, label %271, label %3

3:                                                ; preds = %0
  %4 = load i64, ptr @gc_root_count, align 8, !tbaa !5
  %5 = icmp ugt i64 %4, 1
  br i1 %5, label %12, label %6

6:                                                ; preds = %75, %3
  %7 = phi ptr [ %1, %3 ], [ %76, %75 ]
  %8 = phi i64 [ 0, %3 ], [ %77, %75 ]
  %9 = phi i64 [ 256, %3 ], [ %78, %75 ]
  %10 = load i64, ptr @gc_thread_count, align 8, !tbaa !5
  %11 = icmp eq i64 %10, 0
  br i1 %11, label %83, label %88

12:                                               ; preds = %3, %75
  %13 = phi i64 [ %78, %75 ], [ 256, %3 ]
  %14 = phi i64 [ %77, %75 ], [ 0, %3 ]
  %15 = phi ptr [ %76, %75 ], [ %1, %3 ]
  %16 = phi i64 [ %79, %75 ], [ 0, %3 ]
  %17 = or disjoint i64 %16, 1
  %18 = getelementptr inbounds [512 x i64], ptr @gc_roots, i64 0, i64 %16
  %19 = load i64, ptr %18, align 16, !tbaa !5
  %20 = getelementptr inbounds [512 x i64], ptr @gc_roots, i64 0, i64 %17
  %21 = load i64, ptr %20, align 8, !tbaa !5
  %22 = icmp ult i64 %21, 8
  br i1 %22, label %75, label %23

23:                                               ; preds = %12, %69
  %24 = phi i64 [ %73, %69 ], [ 8, %12 ]
  %25 = phi i64 [ %72, %69 ], [ %13, %12 ]
  %26 = phi i64 [ %71, %69 ], [ %14, %12 ]
  %27 = phi ptr [ %70, %69 ], [ %15, %12 ]
  %28 = phi i64 [ %24, %69 ], [ 0, %12 ]
  %29 = add i64 %28, %19
  %30 = inttoptr i64 %29 to ptr
  %31 = load volatile i64, ptr %30, align 8, !tbaa !5
  %32 = and i64 %31, -2
  %33 = icmp eq i64 %32, 0
  %34 = and i64 %31, 6
  %35 = icmp ne i64 %34, 0
  %36 = or i1 %33, %35
  %37 = load i64, ptr @gc_min, align 8
  %38 = icmp ult i64 %32, %37
  %39 = select i1 %36, i1 true, i1 %38
  br i1 %39, label %69, label %40

40:                                               ; preds = %23
  %41 = load i64, ptr @gc_max, align 8, !tbaa !5
  %42 = icmp ugt i64 %32, %41
  %43 = icmp ult i64 %31, 48
  %44 = or i1 %43, %42
  br i1 %44, label %69, label %45

45:                                               ; preds = %40
  %46 = add i64 %32, -48
  %47 = inttoptr i64 %46 to ptr
  %48 = load i64, ptr %47, align 8, !tbaa !11
  %49 = icmp eq i64 %48, 6073194554910330702
  br i1 %49, label %50, label %69

50:                                               ; preds = %45
  %51 = getelementptr inbounds i8, ptr %47, i64 8
  %52 = load i64, ptr %51, align 8, !tbaa !13
  %53 = icmp ult i64 %52, 48
  %54 = add i64 %52, %46
  %55 = icmp ult i64 %54, %32
  %56 = or i1 %53, %55
  br i1 %56, label %69, label %57

57:                                               ; preds = %50
  %58 = icmp eq i64 %26, %25
  br i1 %58, label %59, label %64

59:                                               ; preds = %57
  %60 = shl i64 %26, 1
  %61 = shl i64 %26, 4
  %62 = tail call ptr @realloc(ptr noundef %27, i64 noundef %61) #19
  %63 = icmp eq ptr %62, null
  br i1 %63, label %75, label %64

64:                                               ; preds = %59, %57
  %65 = phi ptr [ %62, %59 ], [ %27, %57 ]
  %66 = phi i64 [ %60, %59 ], [ %25, %57 ]
  %67 = add i64 %26, 1
  %68 = getelementptr inbounds i64, ptr %65, i64 %26
  store i64 %32, ptr %68, align 8, !tbaa !5
  br label %69

69:                                               ; preds = %50, %45, %40, %23, %64
  %70 = phi ptr [ %65, %64 ], [ %27, %23 ], [ %27, %40 ], [ %27, %45 ], [ %27, %50 ]
  %71 = phi i64 [ %67, %64 ], [ %26, %23 ], [ %26, %40 ], [ %26, %45 ], [ %26, %50 ]
  %72 = phi i64 [ %66, %64 ], [ %25, %23 ], [ %25, %40 ], [ %25, %45 ], [ %25, %50 ]
  %73 = add i64 %24, 8
  %74 = icmp ugt i64 %73, %21
  br i1 %74, label %75, label %23, !llvm.loop !35

75:                                               ; preds = %69, %59, %12
  %76 = phi ptr [ %15, %12 ], [ %70, %69 ], [ %27, %59 ]
  %77 = phi i64 [ %14, %12 ], [ %71, %69 ], [ %26, %59 ]
  %78 = phi i64 [ %13, %12 ], [ %72, %69 ], [ %60, %59 ]
  %79 = add i64 %16, 2
  %80 = or disjoint i64 %79, 1
  %81 = load i64, ptr @gc_root_count, align 8, !tbaa !5
  %82 = icmp ult i64 %80, %81
  br i1 %82, label %12, label %6, !llvm.loop !36

83:                                               ; preds = %162, %6
  %84 = phi ptr [ %7, %6 ], [ %164, %162 ]
  %85 = phi i64 [ %8, %6 ], [ %165, %162 ]
  %86 = phi i64 [ %9, %6 ], [ %166, %162 ]
  %87 = icmp eq i64 %85, 0
  br i1 %87, label %269, label %171

88:                                               ; preds = %6, %162
  %89 = phi i64 [ %163, %162 ], [ %10, %6 ]
  %90 = phi i64 [ %166, %162 ], [ %9, %6 ]
  %91 = phi i64 [ %165, %162 ], [ %8, %6 ]
  %92 = phi ptr [ %164, %162 ], [ %7, %6 ]
  %93 = phi i64 [ %167, %162 ], [ 0, %6 ]
  %94 = getelementptr inbounds [128 x %struct.GCThread], ptr @gc_threads, i64 0, i64 %93
  %95 = getelementptr inbounds i8, ptr %94, i64 8
  %96 = load i64, ptr %95, align 8, !tbaa !18
  %97 = icmp eq i64 %96, 0
  br i1 %97, label %162, label %98

98:                                               ; preds = %88
  %99 = getelementptr inbounds i8, ptr %94, i64 24
  %100 = load i64, ptr %99, align 8, !tbaa !22
  %101 = icmp eq i64 %100, 0
  br i1 %101, label %162, label %102

102:                                              ; preds = %98
  %103 = getelementptr inbounds i8, ptr %94, i64 32
  br label %104

104:                                              ; preds = %102, %150
  %105 = phi i64 [ %100, %102 ], [ %151, %150 ]
  %106 = phi i64 [ %90, %102 ], [ %152, %150 ]
  %107 = phi i64 [ %91, %102 ], [ %153, %150 ]
  %108 = phi ptr [ %92, %102 ], [ %154, %150 ]
  %109 = phi i64 [ 0, %102 ], [ %155, %150 ]
  %110 = getelementptr inbounds [8192 x i64], ptr %103, i64 0, i64 %109
  %111 = load i64, ptr %110, align 8, !tbaa !5
  %112 = and i64 %111, -2
  %113 = icmp eq i64 %112, 0
  %114 = and i64 %111, 6
  %115 = icmp ne i64 %114, 0
  %116 = or i1 %113, %115
  %117 = load i64, ptr @gc_min, align 8
  %118 = icmp ult i64 %112, %117
  %119 = select i1 %116, i1 true, i1 %118
  br i1 %119, label %150, label %120

120:                                              ; preds = %104
  %121 = load i64, ptr @gc_max, align 8, !tbaa !5
  %122 = icmp ugt i64 %112, %121
  %123 = icmp ult i64 %111, 48
  %124 = or i1 %123, %122
  br i1 %124, label %150, label %125

125:                                              ; preds = %120
  %126 = add i64 %112, -48
  %127 = inttoptr i64 %126 to ptr
  %128 = load i64, ptr %127, align 8, !tbaa !11
  %129 = icmp eq i64 %128, 6073194554910330702
  br i1 %129, label %130, label %150

130:                                              ; preds = %125
  %131 = getelementptr inbounds i8, ptr %127, i64 8
  %132 = load i64, ptr %131, align 8, !tbaa !13
  %133 = icmp ult i64 %132, 48
  %134 = add i64 %132, %126
  %135 = icmp ult i64 %134, %112
  %136 = or i1 %133, %135
  br i1 %136, label %150, label %137

137:                                              ; preds = %130
  %138 = icmp eq i64 %107, %106
  br i1 %138, label %139, label %144

139:                                              ; preds = %137
  %140 = shl i64 %106, 1
  %141 = shl i64 %106, 4
  %142 = tail call ptr @realloc(ptr noundef %108, i64 noundef %141) #19
  %143 = icmp eq ptr %142, null
  br i1 %143, label %157, label %144

144:                                              ; preds = %139, %137
  %145 = phi ptr [ %142, %139 ], [ %108, %137 ]
  %146 = phi i64 [ %140, %139 ], [ %106, %137 ]
  %147 = add i64 %107, 1
  %148 = getelementptr inbounds i64, ptr %145, i64 %107
  store i64 %112, ptr %148, align 8, !tbaa !5
  %149 = load i64, ptr %99, align 8, !tbaa !22
  br label %150

150:                                              ; preds = %130, %125, %120, %104, %144
  %151 = phi i64 [ %149, %144 ], [ %105, %104 ], [ %105, %120 ], [ %105, %125 ], [ %105, %130 ]
  %152 = phi i64 [ %146, %144 ], [ %106, %104 ], [ %106, %120 ], [ %106, %125 ], [ %106, %130 ]
  %153 = phi i64 [ %147, %144 ], [ %107, %104 ], [ %107, %120 ], [ %107, %125 ], [ %107, %130 ]
  %154 = phi ptr [ %145, %144 ], [ %108, %104 ], [ %108, %120 ], [ %108, %125 ], [ %108, %130 ]
  %155 = add nuw i64 %109, 1
  %156 = icmp ult i64 %155, %151
  br i1 %156, label %104, label %157, !llvm.loop !37

157:                                              ; preds = %139, %150
  %158 = phi ptr [ %108, %139 ], [ %154, %150 ]
  %159 = phi i64 [ %106, %139 ], [ %153, %150 ]
  %160 = phi i64 [ %140, %139 ], [ %152, %150 ]
  %161 = load i64, ptr @gc_thread_count, align 8, !tbaa !5
  br label %162

162:                                              ; preds = %157, %98, %88
  %163 = phi i64 [ %89, %88 ], [ %89, %98 ], [ %161, %157 ]
  %164 = phi ptr [ %92, %88 ], [ %92, %98 ], [ %158, %157 ]
  %165 = phi i64 [ %91, %88 ], [ %91, %98 ], [ %159, %157 ]
  %166 = phi i64 [ %90, %88 ], [ %90, %98 ], [ %160, %157 ]
  %167 = add nuw nsw i64 %93, 1
  %168 = icmp ult i64 %167, %163
  %169 = icmp ult i64 %93, 127
  %170 = and i1 %169, %168
  br i1 %170, label %88, label %83, !llvm.loop !38

171:                                              ; preds = %83, %264
  %172 = phi i64 [ %267, %264 ], [ %86, %83 ]
  %173 = phi i64 [ %266, %264 ], [ %85, %83 ]
  %174 = phi ptr [ %265, %264 ], [ %84, %83 ]
  %175 = add i64 %173, -1
  %176 = getelementptr inbounds i64, ptr %174, i64 %175
  %177 = load i64, ptr %176, align 8, !tbaa !5
  %178 = and i64 %177, -2
  %179 = icmp eq i64 %178, 0
  %180 = and i64 %177, 6
  %181 = icmp ne i64 %180, 0
  %182 = or i1 %179, %181
  %183 = load i64, ptr @gc_min, align 8
  %184 = icmp ult i64 %178, %183
  %185 = select i1 %182, i1 true, i1 %184
  br i1 %185, label %264, label %186

186:                                              ; preds = %171
  %187 = load i64, ptr @gc_max, align 8, !tbaa !5
  %188 = icmp ugt i64 %178, %187
  %189 = icmp ult i64 %177, 48
  %190 = or i1 %189, %188
  br i1 %190, label %264, label %191

191:                                              ; preds = %186
  %192 = add i64 %178, -48
  %193 = inttoptr i64 %192 to ptr
  %194 = load i64, ptr %193, align 8, !tbaa !11
  %195 = icmp eq i64 %194, 6073194554910330702
  br i1 %195, label %196, label %264

196:                                              ; preds = %191
  %197 = getelementptr inbounds i8, ptr %193, i64 8
  %198 = load i64, ptr %197, align 8, !tbaa !13
  %199 = icmp ult i64 %198, 48
  %200 = add i64 %198, %192
  %201 = icmp ult i64 %200, %178
  %202 = or i1 %199, %201
  br i1 %202, label %264, label %203, !llvm.loop !39

203:                                              ; preds = %196
  %204 = load atomic i64, ptr @gc_epoch seq_cst, align 8
  %205 = getelementptr inbounds i8, ptr %193, i64 16
  %206 = load atomic i64, ptr %205 seq_cst, align 8
  %207 = icmp eq i64 %206, %204
  br i1 %207, label %264, label %208, !llvm.loop !39

208:                                              ; preds = %203
  store atomic i64 %204, ptr %205 seq_cst, align 8
  %209 = load i64, ptr %197, align 8, !tbaa !13
  %210 = add i64 %209, %192
  %211 = add i64 %178, 8
  %212 = icmp ugt i64 %211, %210
  br i1 %212, label %264, label %213

213:                                              ; preds = %208, %258
  %214 = phi i64 [ %262, %258 ], [ %211, %208 ]
  %215 = phi i64 [ %261, %258 ], [ %172, %208 ]
  %216 = phi i64 [ %260, %258 ], [ %175, %208 ]
  %217 = phi i64 [ %214, %258 ], [ %178, %208 ]
  %218 = phi ptr [ %259, %258 ], [ %174, %208 ]
  %219 = inttoptr i64 %217 to ptr
  %220 = load volatile i64, ptr %219, align 8, !tbaa !5
  %221 = and i64 %220, -2
  %222 = icmp eq i64 %221, 0
  %223 = and i64 %220, 6
  %224 = icmp ne i64 %223, 0
  %225 = or i1 %222, %224
  %226 = load i64, ptr @gc_min, align 8
  %227 = icmp ult i64 %221, %226
  %228 = select i1 %225, i1 true, i1 %227
  br i1 %228, label %258, label %229

229:                                              ; preds = %213
  %230 = load i64, ptr @gc_max, align 8, !tbaa !5
  %231 = icmp ugt i64 %221, %230
  %232 = icmp ult i64 %220, 48
  %233 = or i1 %232, %231
  br i1 %233, label %258, label %234

234:                                              ; preds = %229
  %235 = add i64 %221, -48
  %236 = inttoptr i64 %235 to ptr
  %237 = load i64, ptr %236, align 8, !tbaa !11
  %238 = icmp eq i64 %237, 6073194554910330702
  br i1 %238, label %239, label %258

239:                                              ; preds = %234
  %240 = getelementptr inbounds i8, ptr %236, i64 8
  %241 = load i64, ptr %240, align 8, !tbaa !13
  %242 = icmp ult i64 %241, 48
  %243 = add i64 %241, %235
  %244 = icmp ult i64 %243, %221
  %245 = or i1 %242, %244
  br i1 %245, label %258, label %246

246:                                              ; preds = %239
  %247 = icmp eq i64 %216, %215
  br i1 %247, label %248, label %253

248:                                              ; preds = %246
  %249 = shl i64 %216, 1
  %250 = shl i64 %216, 4
  %251 = tail call ptr @realloc(ptr noundef %218, i64 noundef %250) #19
  %252 = icmp eq ptr %251, null
  br i1 %252, label %264, label %253

253:                                              ; preds = %248, %246
  %254 = phi ptr [ %251, %248 ], [ %218, %246 ]
  %255 = phi i64 [ %249, %248 ], [ %215, %246 ]
  %256 = add i64 %216, 1
  %257 = getelementptr inbounds i64, ptr %254, i64 %216
  store i64 %221, ptr %257, align 8, !tbaa !5
  br label %258

258:                                              ; preds = %239, %234, %229, %213, %253
  %259 = phi ptr [ %254, %253 ], [ %218, %213 ], [ %218, %229 ], [ %218, %234 ], [ %218, %239 ]
  %260 = phi i64 [ %256, %253 ], [ %216, %213 ], [ %216, %229 ], [ %216, %234 ], [ %216, %239 ]
  %261 = phi i64 [ %255, %253 ], [ %215, %213 ], [ %215, %229 ], [ %215, %234 ], [ %215, %239 ]
  %262 = add i64 %214, 8
  %263 = icmp ugt i64 %262, %210
  br i1 %263, label %264, label %213, !llvm.loop !40

264:                                              ; preds = %258, %248, %208, %196, %191, %186, %171, %203
  %265 = phi ptr [ %174, %203 ], [ %174, %171 ], [ %174, %186 ], [ %174, %191 ], [ %174, %196 ], [ %174, %208 ], [ %218, %248 ], [ %259, %258 ]
  %266 = phi i64 [ %175, %203 ], [ %175, %171 ], [ %175, %186 ], [ %175, %191 ], [ %175, %196 ], [ %175, %208 ], [ %216, %248 ], [ %260, %258 ]
  %267 = phi i64 [ %172, %203 ], [ %172, %171 ], [ %172, %186 ], [ %172, %191 ], [ %172, %196 ], [ %172, %208 ], [ %249, %248 ], [ %261, %258 ]
  %268 = icmp eq i64 %266, 0
  br i1 %268, label %269, label %171

269:                                              ; preds = %264, %83
  %270 = phi ptr [ %84, %83 ], [ %265, %264 ]
  tail call void @free(ptr noundef %270) #15
  br label %271

271:                                              ; preds = %0, %269
  ret void
}

declare i32 @nanosleep(ptr noundef, ptr noundef) local_unnamed_addr #11

; Function Attrs: mustprogress nounwind willreturn allockind("realloc") allocsize(1) memory(argmem: readwrite, inaccessiblemem: readwrite)
declare noalias noundef ptr @realloc(ptr allocptr nocapture noundef, i64 noundef) local_unnamed_addr #12

; Function Attrs: nounwind
declare void @free(ptr noundef) local_unnamed_addr #4

; Function Attrs: nocallback nofree nounwind willreturn memory(argmem: write)
declare void @llvm.memset.p0.i64(ptr nocapture writeonly, i8, i64, i1 immarg) #13

attributes #0 = { nounwind uwtable "min-legal-vector-width"="0" "no-builtin-free" "no-builtin-malloc" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #1 = { mustprogress nocallback nofree nosync nounwind willreturn memory(argmem: readwrite) }
attributes #2 = { nofree nounwind memory(read) "no-builtin-free" "no-builtin-malloc" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #3 = { mustprogress nofree nounwind willreturn "no-builtin-free" "no-builtin-malloc" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #4 = { nounwind "no-builtin-free" "no-builtin-malloc" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #5 = { cold noreturn nounwind "no-builtin-free" "no-builtin-malloc" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #6 = { mustprogress nocallback nofree nosync nounwind speculatable willreturn memory(none) }
attributes #7 = { mustprogress nofree nosync nounwind willreturn memory(none) "no-builtin-free" "no-builtin-malloc" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #8 = { mustprogress nofree norecurse nosync nounwind willreturn memory(readwrite, argmem: none, inaccessiblemem: none) uwtable "min-legal-vector-width"="0" "no-builtin-free" "no-builtin-malloc" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #9 = { nofree nounwind "no-builtin-free" "no-builtin-malloc" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #10 = { mustprogress nocallback nofree nosync nounwind willreturn memory(none) }
attributes #11 = { "no-builtin-free" "no-builtin-malloc" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #12 = { mustprogress nounwind willreturn allockind("realloc") allocsize(1) memory(argmem: readwrite, inaccessiblemem: readwrite) "alloc-family"="malloc" "no-builtin-free" "no-builtin-malloc" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #13 = { nocallback nofree nounwind willreturn memory(argmem: write) }
attributes #14 = { nounwind "no-builtin-free" "no-builtin-malloc" }
attributes #15 = { nobuiltin nounwind "no-builtin-free" "no-builtin-malloc" }
attributes #16 = { cold noreturn nounwind "no-builtin-free" "no-builtin-malloc" }
attributes #17 = { nounwind }
attributes #18 = { "no-builtin-free" "no-builtin-malloc" }
attributes #19 = { nounwind allocsize(1) "no-builtin-free" "no-builtin-malloc" }
attributes #20 = { nounwind willreturn memory(none) "no-builtin-free" "no-builtin-malloc" }

!llvm.module.flags = !{!0, !1, !2, !3}
!llvm.ident = !{!4}

!0 = !{i32 1, !"wchar_size", i32 4}
!1 = !{i32 8, !"PIC Level", i32 2}
!2 = !{i32 7, !"PIE Level", i32 2}
!3 = !{i32 7, !"uwtable", i32 2}
!4 = !{!"Debian clang version 19.1.7 (3+b1)"}
!5 = !{!6, !6, i64 0}
!6 = !{!"long", !7, i64 0}
!7 = !{!"omnipotent char", !8, i64 0}
!8 = !{!"Simple C/C++ TBAA"}
!9 = distinct !{!9, !10}
!10 = !{!"llvm.loop.mustprogress"}
!11 = !{!12, !6, i64 0}
!12 = !{!"GCBlock", !6, i64 0, !6, i64 8, !6, i64 16, !6, i64 24, !6, i64 32, !6, i64 40}
!13 = !{!12, !6, i64 8}
!14 = !{!12, !6, i64 16}
!15 = !{!12, !6, i64 24}
!16 = !{!17, !6, i64 16}
!17 = !{!"", !6, i64 0, !6, i64 8, !6, i64 16, !6, i64 24, !7, i64 32}
!18 = !{!17, !6, i64 8}
!19 = !{!20, !6, i64 0}
!20 = !{!"timespec", !6, i64 0, !6, i64 8}
!21 = !{!20, !6, i64 8}
!22 = !{!17, !6, i64 24}
!23 = distinct !{!23, !10}
!24 = distinct !{!24, !10}
!25 = distinct !{!25, !10}
!26 = distinct !{!26, !10}
!27 = distinct !{!27, !10}
!28 = distinct !{!28, !10}
!29 = distinct !{!29, !10}
!30 = distinct !{!30, !10}
!31 = distinct !{!31, !10}
!32 = distinct !{!32, !10}
!33 = !{!17, !6, i64 0}
!34 = distinct !{!34, !10}
!35 = distinct !{!35, !10}
!36 = distinct !{!36, !10}
!37 = distinct !{!37, !10}
!38 = distinct !{!38, !10}
!39 = distinct !{!39, !10}
!40 = distinct !{!40, !10}
