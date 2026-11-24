
%struct.GCThread = type { i64, i64, i64, i64, [8192 x i64] }
%struct.timespec = type { i64, i64 }

@gc_collecting = internal unnamed_addr global i64 0, align 8
@gc_epoch = internal global i64 1, align 8
@gc_head = internal unnamed_addr global i64 0, align 8
@gc_min = internal unnamed_addr global i64 -1, align 8
@gc_max = internal unnamed_addr global i64 0, align 8
@gc_root_count = internal unnamed_addr global i64 0, align 8
@gc_roots = internal unnamed_addr global [512 x i64] zeroinitializer, align 16
@gc_thread_count = internal unnamed_addr global i64 0, align 8
@gc_my_id = internal thread_local unnamed_addr global i64 0, align 8
@gc_threads = internal unnamed_addr global [128 x %struct.GCThread] zeroinitializer, align 16
@gc_stats = internal unnamed_addr global i1 false, align 4
@gc_collections = internal global i64 0, align 8
@gc_snap_gen = internal global i64 0, align 8
@gc_max_mark_ns = internal global i64 0, align 8
@gc_max_sweep_ns = internal global i64 0, align 8
@gc_sum_collector_ns = internal global i64 0, align 8
@__gc_str = private unnamed_addr constant [134 x i8] c"[gc] collections=%llu snapshots=%llu snapshot_max=%.0fus snapshot_avg=%.0fus mark_max=%.0fus sweep_max=%.0fus collector_total=%.1fms\0A\00", align 1
@gc_snapshot_count = internal global i64 0, align 8
@gc_max_snapshot_ns = internal global i64 0, align 8
@gc_sum_snapshot_ns = internal global i64 0, align 8
@gc_env_initialized = internal unnamed_addr global i1 false, align 4
@__gc_str_1 = private unnamed_addr constant [18 x i8] c"THREADON_GC_STATS\00", align 1
@gc_lock = internal global i8 0, align 1

; Function Attrs: nounwind uwtable
define dso_local nonnull ptr @__threadon_gc_alloc(i64 noundef %0, i64 noundef %1) local_unnamed_addr #0 {
  %3 = load i1, ptr @gc_env_initialized, align 4
  br i1 %3, label %16, label %4

4:                                                ; preds = %2
  %5 = tail call ptr @getenv(ptr noundef nonnull @__gc_str_1) #15
  %6 = icmp eq ptr %5, null
  br i1 %6, label %15, label %7

7:                                                ; preds = %4
  %8 = load i8, ptr %5, align 1
  %9 = icmp eq i8 %8, 48
  br i1 %9, label %10, label %14

10:                                               ; preds = %7
  %11 = getelementptr inbounds i8, ptr %5, i64 1
  %12 = load i8, ptr %11, align 1
  %13 = icmp eq i8 %12, 0
  br i1 %13, label %15, label %14

14:                                               ; preds = %10, %7
  store i1 true, ptr @gc_stats, align 4
  br label %15

15:                                               ; preds = %14, %10, %4
  store i1 true, ptr @gc_env_initialized, align 4
  br label %16

16:                                               ; preds = %2, %15
  %17 = add i64 %0, 55
  %18 = and i64 %17, -8
  %19 = icmp ult i64 %17, 48
  %20 = select i1 %19, i64 48, i64 %18
  %21 = tail call noalias ptr @malloc(i64 noundef %20) #16
  %22 = icmp eq ptr %21, null
  br i1 %22, label %23, label %24

23:                                               ; preds = %16
  tail call void @abort() #17
  unreachable

24:                                               ; preds = %16
  %25 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %26 = icmp eq i8 %25, 0
  br i1 %26, label %31, label %27

27:                                               ; preds = %24, %27
  %28 = tail call i32 @sched_yield() #15
  %29 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %30 = icmp eq i8 %29, 0
  br i1 %30, label %31, label %27, !llvm.loop !5

31:                                               ; preds = %27, %24
  store i64 6073194554910330702, ptr %21, align 8, !tbaa !7
  %32 = getelementptr inbounds i8, ptr %21, i64 8
  store i64 %20, ptr %32, align 8, !tbaa !12
  %33 = getelementptr inbounds i8, ptr %21, i64 32
  store i64 1, ptr %33, align 8, !tbaa !13
  %34 = getelementptr inbounds i8, ptr %21, i64 40
  store i64 0, ptr %34, align 8, !tbaa !14
  %35 = load atomic i64, ptr @gc_collecting seq_cst, align 8
  %36 = icmp eq i64 %35, 0
  br i1 %36, label %39, label %37

37:                                               ; preds = %31
  %38 = load atomic i64, ptr @gc_epoch seq_cst, align 8
  br label %39

39:                                               ; preds = %31, %37
  %40 = phi i64 [ %38, %37 ], [ 0, %31 ]
  %41 = getelementptr inbounds i8, ptr %21, i64 16
  store i64 %40, ptr %41, align 8, !tbaa !15
  %42 = load i64, ptr @gc_head, align 8, !tbaa !16
  %43 = getelementptr inbounds i8, ptr %21, i64 24
  store i64 %42, ptr %43, align 8, !tbaa !17
  %44 = ptrtoint ptr %21 to i64
  store i64 %44, ptr @gc_head, align 8, !tbaa !16
  %45 = load i64, ptr @gc_min, align 8, !tbaa !16
  %46 = icmp ugt i64 %45, %44
  br i1 %46, label %47, label %48

47:                                               ; preds = %39
  store i64 %44, ptr @gc_min, align 8, !tbaa !16
  br label %48

48:                                               ; preds = %47, %39
  %49 = add i64 %20, %44
  %50 = load i64, ptr @gc_max, align 8, !tbaa !16
  %51 = icmp ugt i64 %49, %50
  br i1 %51, label %52, label %53

52:                                               ; preds = %48
  store i64 %49, ptr @gc_max, align 8, !tbaa !16
  br label %53

53:                                               ; preds = %52, %48
  store atomic volatile i8 0, ptr @gc_lock release, align 1
  tail call fastcc void @gc_capture_stack() #18
  %54 = getelementptr inbounds i8, ptr %21, i64 48
  ret ptr %54
}

; Function Attrs: mustprogress nocallback nofree nosync nounwind willreturn memory(argmem: readwrite)
declare void @llvm.lifetime.start.p0(i64 immarg, ptr nocapture) #1

; Function Attrs: nounwind
declare noalias ptr @malloc(i64 noundef) local_unnamed_addr #2

; Function Attrs: cold noreturn nounwind
declare void @abort() local_unnamed_addr #3

; Function Attrs: nounwind uwtable
define internal fastcc void @gc_capture_stack() unnamed_addr #0 {
  %1 = alloca %struct.timespec, align 8
  %2 = alloca %struct.timespec, align 8
  %3 = tail call align 8 ptr @llvm.threadlocal.address.p0(ptr align 8 @gc_my_id)
  %4 = load i64, ptr %3, align 8, !tbaa !16
  %5 = add i64 %4, -129
  %6 = icmp ult i64 %5, -128
  br i1 %6, label %107, label %7

7:                                                ; preds = %0
  %8 = add nsw i64 %4, -1
  %9 = getelementptr inbounds [128 x %struct.GCThread], ptr @gc_threads, i64 0, i64 %8
  %10 = load atomic i64, ptr @gc_snap_gen seq_cst, align 8
  %11 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %12 = icmp eq i8 %11, 0
  br i1 %12, label %17, label %13

13:                                               ; preds = %7, %13
  %14 = tail call i32 @sched_yield() #15
  %15 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %16 = icmp eq i8 %15, 0
  br i1 %16, label %17, label %13, !llvm.loop !5

17:                                               ; preds = %13, %7
  %18 = getelementptr inbounds i8, ptr %9, i64 16
  %19 = load i64, ptr %18, align 16, !tbaa !18
  %20 = icmp eq i64 %19, %10
  br i1 %20, label %21, label %22

21:                                               ; preds = %17
  store atomic volatile i8 0, ptr @gc_lock release, align 1
  br label %107

22:                                               ; preds = %17
  %23 = tail call ptr @llvm.frameaddress.p0(i32 0)
  %24 = ptrtoint ptr %23 to i64
  %25 = getelementptr inbounds i8, ptr %9, i64 8
  %26 = load i64, ptr %25, align 8, !tbaa !20
  %27 = load i1, ptr @gc_stats, align 4
  br i1 %27, label %28, label %35

28:                                               ; preds = %22
  call void @llvm.lifetime.start.p0(i64 16, ptr nonnull %2) #19
  %29 = call i32 @clock_gettime(i32 noundef 1, ptr noundef nonnull %2) #15
  %30 = load i64, ptr %2, align 8, !tbaa !21
  %31 = mul i64 %30, -1000000000
  %32 = getelementptr inbounds i8, ptr %2, i64 8
  %33 = load i64, ptr %32, align 8, !tbaa !23
  %34 = sub i64 %31, %33
  call void @llvm.lifetime.end.p0(i64 16, ptr nonnull %2) #19
  br label %35

35:                                               ; preds = %22, %28
  %36 = phi i64 [ %34, %28 ], [ 0, %22 ]
  %37 = icmp ne i64 %26, 0
  %38 = icmp ugt i64 %26, %24
  %39 = select i1 %37, i1 %38, i1 false
  br i1 %39, label %40, label %85

40:                                               ; preds = %35
  %41 = add i64 %24, 8
  %42 = icmp ugt i64 %41, %26
  br i1 %42, label %85, label %43

43:                                               ; preds = %40
  %44 = load i64, ptr @gc_min, align 8
  %45 = load i64, ptr @gc_max, align 8
  %46 = getelementptr inbounds i8, ptr %9, i64 32
  br label %47

47:                                               ; preds = %43, %79
  %48 = phi i64 [ %41, %43 ], [ %81, %79 ]
  %49 = phi i64 [ 0, %43 ], [ %80, %79 ]
  %50 = phi ptr [ %23, %43 ], [ %51, %79 ]
  %51 = inttoptr i64 %48 to ptr
  %52 = load volatile i64, ptr %50, align 8, !tbaa !16
  %53 = and i64 %52, -2
  %54 = icmp eq i64 %53, 0
  %55 = and i64 %52, 6
  %56 = icmp ne i64 %55, 0
  %57 = or i1 %54, %56
  %58 = icmp ult i64 %53, %44
  %59 = select i1 %57, i1 true, i1 %58
  br i1 %59, label %79, label %60

60:                                               ; preds = %47
  %61 = icmp ugt i64 %53, %45
  %62 = icmp ult i64 %52, 48
  %63 = or i1 %62, %61
  br i1 %63, label %79, label %64

64:                                               ; preds = %60
  %65 = add i64 %53, -48
  %66 = inttoptr i64 %65 to ptr
  %67 = load i64, ptr %66, align 8, !tbaa !7
  %68 = icmp eq i64 %67, 6073194554910330702
  br i1 %68, label %69, label %79

69:                                               ; preds = %64
  %70 = getelementptr inbounds i8, ptr %66, i64 8
  %71 = load i64, ptr %70, align 8, !tbaa !12
  %72 = icmp ult i64 %71, 48
  %73 = add i64 %71, %65
  %74 = icmp ult i64 %73, %53
  %75 = or i1 %72, %74
  br i1 %75, label %79, label %76

76:                                               ; preds = %69
  %77 = add nuw nsw i64 %49, 1
  %78 = getelementptr inbounds [8192 x i64], ptr %46, i64 0, i64 %49
  store i64 %53, ptr %78, align 8, !tbaa !16
  br label %79

79:                                               ; preds = %69, %64, %60, %47, %76
  %80 = phi i64 [ %77, %76 ], [ %49, %47 ], [ %49, %60 ], [ %49, %64 ], [ %49, %69 ]
  %81 = add i64 %48, 8
  %82 = icmp ule i64 %81, %26
  %83 = icmp ult i64 %80, 8192
  %84 = select i1 %82, i1 %83, i1 false
  br i1 %84, label %47, label %85, !llvm.loop !24

85:                                               ; preds = %79, %40, %35
  %86 = phi i64 [ 0, %35 ], [ 0, %40 ], [ %80, %79 ]
  %87 = getelementptr inbounds i8, ptr %9, i64 24
  store i64 %86, ptr %87, align 8, !tbaa !25
  store atomic i64 %10, ptr %18 seq_cst, align 16
  store atomic volatile i8 0, ptr @gc_lock release, align 1
  %88 = load i1, ptr @gc_stats, align 4
  br i1 %88, label %89, label %107

89:                                               ; preds = %85
  call void @llvm.lifetime.start.p0(i64 16, ptr nonnull %1) #19
  %90 = call i32 @clock_gettime(i32 noundef 1, ptr noundef nonnull %1) #15
  %91 = load i64, ptr %1, align 8, !tbaa !21
  %92 = mul i64 %91, 1000000000
  %93 = getelementptr inbounds i8, ptr %1, i64 8
  %94 = load i64, ptr %93, align 8, !tbaa !23
  call void @llvm.lifetime.end.p0(i64 16, ptr nonnull %1) #19
  %95 = add i64 %94, %36
  %96 = add i64 %95, %92
  %97 = atomicrmw add ptr @gc_sum_snapshot_ns, i64 %96 monotonic, align 8
  %98 = atomicrmw add ptr @gc_snapshot_count, i64 1 monotonic, align 8
  %99 = load atomic i64, ptr @gc_max_snapshot_ns monotonic, align 8
  br label %100

100:                                              ; preds = %103, %89
  %101 = phi i64 [ %99, %89 ], [ %106, %103 ]
  %102 = icmp ult i64 %101, %96
  br i1 %102, label %103, label %107

103:                                              ; preds = %100
  %104 = cmpxchg ptr @gc_max_snapshot_ns, i64 %101, i64 %96 monotonic monotonic, align 8
  %105 = extractvalue { i64, i1 } %104, 1
  %106 = extractvalue { i64, i1 } %104, 0
  br i1 %105, label %107, label %100, !llvm.loop !26

107:                                              ; preds = %103, %100, %21, %85, %0
  ret void
}

; Function Attrs: mustprogress nocallback nofree nosync nounwind willreturn memory(argmem: readwrite)
declare void @llvm.lifetime.end.p0(i64 immarg, ptr nocapture) #1

; Function Attrs: nounwind uwtable
define dso_local void @__threadon_gc_barrier(i64 noundef %0, i64 noundef %1) local_unnamed_addr #0 {
  %3 = load atomic i64, ptr @gc_collecting seq_cst, align 8
  %4 = icmp eq i64 %3, 0
  %5 = icmp ult i64 %1, 8
  %6 = or i1 %4, %5
  br i1 %6, label %161, label %7

7:                                                ; preds = %2, %158
  %8 = phi i64 [ %159, %158 ], [ 8, %2 ]
  %9 = phi i64 [ %8, %158 ], [ 0, %2 ]
  %10 = add i64 %9, %0
  %11 = inttoptr i64 %10 to ptr
  %12 = load volatile i64, ptr %11, align 8, !tbaa !16
  %13 = and i64 %12, -2
  %14 = icmp eq i64 %13, 0
  %15 = and i64 %12, 6
  %16 = icmp ne i64 %15, 0
  %17 = or i1 %14, %16
  %18 = load i64, ptr @gc_min, align 8
  %19 = icmp ult i64 %13, %18
  %20 = select i1 %17, i1 true, i1 %19
  br i1 %20, label %158, label %21

21:                                               ; preds = %7
  %22 = load i64, ptr @gc_max, align 8
  %23 = icmp ugt i64 %13, %22
  %24 = icmp ult i64 %12, 48
  %25 = or i1 %24, %23
  br i1 %25, label %158, label %26

26:                                               ; preds = %21
  %27 = add i64 %13, -48
  %28 = inttoptr i64 %27 to ptr
  %29 = load i64, ptr %28, align 8, !tbaa !7
  %30 = icmp eq i64 %29, 6073194554910330702
  br i1 %30, label %31, label %158

31:                                               ; preds = %26
  %32 = getelementptr inbounds i8, ptr %28, i64 8
  %33 = load i64, ptr %32, align 8, !tbaa !12
  %34 = icmp ult i64 %33, 48
  %35 = add i64 %33, %27
  %36 = icmp ult i64 %35, %13
  %37 = or i1 %34, %36
  br i1 %37, label %158, label %38

38:                                               ; preds = %31
  %39 = tail call noalias ptr @malloc(i64 noundef 2048) #16
  %40 = icmp eq ptr %39, null
  br i1 %40, label %158, label %41

41:                                               ; preds = %38
  %42 = load i64, ptr @gc_min, align 8
  %43 = icmp ult i64 %13, %42
  %44 = load i64, ptr @gc_max, align 8
  %45 = icmp ugt i64 %13, %44
  %46 = select i1 %43, i1 true, i1 %45
  br i1 %46, label %156, label %47

47:                                               ; preds = %41
  %48 = load i64, ptr %28, align 8, !tbaa !7
  %49 = icmp eq i64 %48, 6073194554910330702
  br i1 %49, label %50, label %156

50:                                               ; preds = %47
  %51 = load i64, ptr %32, align 8, !tbaa !12
  %52 = icmp ult i64 %51, 48
  %53 = add i64 %51, %27
  %54 = icmp ult i64 %53, %13
  %55 = or i1 %52, %54
  br i1 %55, label %156, label %56

56:                                               ; preds = %50
  store i64 %13, ptr %39, align 8, !tbaa !16
  br label %57

57:                                               ; preds = %151, %56
  %58 = phi ptr [ %154, %151 ], [ %39, %56 ]
  %59 = phi i64 [ %153, %151 ], [ 1, %56 ]
  %60 = phi i64 [ %152, %151 ], [ 256, %56 ]
  %61 = add i64 %59, -1
  %62 = getelementptr inbounds i64, ptr %58, i64 %61
  %63 = load i64, ptr %62, align 8, !tbaa !16
  %64 = and i64 %63, -2
  %65 = icmp eq i64 %64, 0
  %66 = and i64 %63, 6
  %67 = icmp ne i64 %66, 0
  %68 = or i1 %65, %67
  %69 = load i64, ptr @gc_min, align 8
  %70 = icmp ult i64 %64, %69
  %71 = select i1 %68, i1 true, i1 %70
  br i1 %71, label %151, label %72

72:                                               ; preds = %57
  %73 = load i64, ptr @gc_max, align 8, !tbaa !16
  %74 = icmp ugt i64 %64, %73
  %75 = icmp ult i64 %63, 48
  %76 = or i1 %75, %74
  br i1 %76, label %151, label %77

77:                                               ; preds = %72
  %78 = add i64 %64, -48
  %79 = inttoptr i64 %78 to ptr
  %80 = load i64, ptr %79, align 8, !tbaa !7
  %81 = icmp eq i64 %80, 6073194554910330702
  br i1 %81, label %82, label %151

82:                                               ; preds = %77
  %83 = getelementptr inbounds i8, ptr %79, i64 8
  %84 = load i64, ptr %83, align 8, !tbaa !12
  %85 = icmp ult i64 %84, 48
  %86 = add i64 %84, %78
  %87 = icmp ult i64 %86, %64
  %88 = or i1 %85, %87
  br i1 %88, label %151, label %89, !llvm.loop !27

89:                                               ; preds = %82
  %90 = load atomic i64, ptr @gc_epoch seq_cst, align 8
  %91 = getelementptr inbounds i8, ptr %79, i64 16
  %92 = load atomic i64, ptr %91 seq_cst, align 8
  %93 = icmp eq i64 %92, %90
  br i1 %93, label %151, label %94, !llvm.loop !27

94:                                               ; preds = %89
  store atomic i64 %90, ptr %91 seq_cst, align 8
  %95 = load i64, ptr %83, align 8, !tbaa !12
  %96 = add i64 %95, %78
  %97 = add i64 %64, 8
  %98 = icmp ugt i64 %97, %96
  br i1 %98, label %151, label %99

99:                                               ; preds = %94, %145
  %100 = phi i64 [ %149, %145 ], [ %97, %94 ]
  %101 = phi i64 [ %100, %145 ], [ %64, %94 ]
  %102 = phi ptr [ %148, %145 ], [ %58, %94 ]
  %103 = phi i64 [ %147, %145 ], [ %61, %94 ]
  %104 = phi i64 [ %146, %145 ], [ %60, %94 ]
  %105 = inttoptr i64 %101 to ptr
  %106 = load volatile i64, ptr %105, align 8, !tbaa !16
  %107 = and i64 %106, -2
  %108 = icmp eq i64 %107, 0
  %109 = and i64 %106, 6
  %110 = icmp ne i64 %109, 0
  %111 = or i1 %108, %110
  %112 = load i64, ptr @gc_min, align 8
  %113 = icmp ult i64 %107, %112
  %114 = select i1 %111, i1 true, i1 %113
  br i1 %114, label %145, label %115

115:                                              ; preds = %99
  %116 = load i64, ptr @gc_max, align 8, !tbaa !16
  %117 = icmp ugt i64 %107, %116
  %118 = icmp ult i64 %106, 48
  %119 = or i1 %118, %117
  br i1 %119, label %145, label %120

120:                                              ; preds = %115
  %121 = add i64 %107, -48
  %122 = inttoptr i64 %121 to ptr
  %123 = load i64, ptr %122, align 8, !tbaa !7
  %124 = icmp eq i64 %123, 6073194554910330702
  br i1 %124, label %125, label %145

125:                                              ; preds = %120
  %126 = getelementptr inbounds i8, ptr %122, i64 8
  %127 = load i64, ptr %126, align 8, !tbaa !12
  %128 = icmp ult i64 %127, 48
  %129 = add i64 %127, %121
  %130 = icmp ult i64 %129, %107
  %131 = or i1 %128, %130
  br i1 %131, label %145, label %132

132:                                              ; preds = %125
  %133 = icmp eq i64 %103, %104
  br i1 %133, label %134, label %140

134:                                              ; preds = %132
  %135 = shl i64 %103, 4
  %136 = tail call ptr @realloc(ptr noundef %102, i64 noundef %135) #20
  %137 = icmp eq ptr %136, null
  br i1 %137, label %145, label %138

138:                                              ; preds = %134
  %139 = shl i64 %103, 1
  br label %140

140:                                              ; preds = %138, %132
  %141 = phi i64 [ %139, %138 ], [ %104, %132 ]
  %142 = phi ptr [ %136, %138 ], [ %102, %132 ]
  %143 = add i64 %103, 1
  %144 = getelementptr inbounds i64, ptr %142, i64 %103
  store i64 %107, ptr %144, align 8, !tbaa !16
  br label %145

145:                                              ; preds = %140, %134, %125, %120, %115, %99
  %146 = phi i64 [ %104, %99 ], [ %104, %115 ], [ %104, %125 ], [ %103, %134 ], [ %141, %140 ], [ %104, %120 ]
  %147 = phi i64 [ %103, %99 ], [ %103, %115 ], [ %103, %125 ], [ %103, %134 ], [ %143, %140 ], [ %103, %120 ]
  %148 = phi ptr [ %102, %99 ], [ %102, %115 ], [ %102, %125 ], [ %102, %134 ], [ %142, %140 ], [ %102, %120 ]
  %149 = add i64 %100, 8
  %150 = icmp ugt i64 %149, %96
  br i1 %150, label %151, label %99, !llvm.loop !28

151:                                              ; preds = %145, %94, %89, %82, %77, %72, %57
  %152 = phi i64 [ %60, %89 ], [ %60, %57 ], [ %60, %72 ], [ %60, %77 ], [ %60, %82 ], [ %60, %94 ], [ %146, %145 ]
  %153 = phi i64 [ %61, %89 ], [ %61, %57 ], [ %61, %72 ], [ %61, %77 ], [ %61, %82 ], [ %61, %94 ], [ %147, %145 ]
  %154 = phi ptr [ %58, %89 ], [ %58, %57 ], [ %58, %72 ], [ %58, %77 ], [ %58, %82 ], [ %58, %94 ], [ %148, %145 ]
  %155 = icmp eq i64 %153, 0
  br i1 %155, label %156, label %57

156:                                              ; preds = %151, %50, %47, %41
  %157 = phi ptr [ %39, %41 ], [ %39, %50 ], [ %39, %47 ], [ %154, %151 ]
  tail call void @free(ptr noundef %157) #16
  br label %158

158:                                              ; preds = %31, %26, %21, %7, %156, %38
  %159 = add i64 %8, 8
  %160 = icmp ugt i64 %159, %1
  br i1 %160, label %161, label %7, !llvm.loop !29

161:                                              ; preds = %158, %2
  ret void
}

; Function Attrs: nounwind uwtable
define dso_local void @__threadon_gc_add_root(ptr noundef %0, i64 noundef %1) local_unnamed_addr #0 {
  %3 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %4 = icmp eq i8 %3, 0
  br i1 %4, label %9, label %5

5:                                                ; preds = %2, %5
  %6 = tail call i32 @sched_yield() #15
  %7 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %8 = icmp eq i8 %7, 0
  br i1 %8, label %9, label %5, !llvm.loop !5

9:                                                ; preds = %5, %2
  %10 = load i64, ptr @gc_root_count, align 8, !tbaa !16
  %11 = add i64 %10, 1
  %12 = icmp ult i64 %11, 512
  br i1 %12, label %13, label %18

13:                                               ; preds = %9
  %14 = ptrtoint ptr %0 to i64
  %15 = getelementptr inbounds [512 x i64], ptr @gc_roots, i64 0, i64 %10
  store i64 %14, ptr %15, align 8, !tbaa !16
  %16 = add nsw i64 %10, 2
  store i64 %16, ptr @gc_root_count, align 8, !tbaa !16
  %17 = getelementptr inbounds [512 x i64], ptr @gc_roots, i64 0, i64 %11
  store i64 %1, ptr %17, align 8, !tbaa !16
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
  %5 = tail call i32 @sched_yield() #15
  %6 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %7 = icmp eq i8 %6, 0
  br i1 %7, label %8, label %4, !llvm.loop !5

8:                                                ; preds = %4, %1
  %9 = load i64, ptr @gc_thread_count, align 8, !tbaa !16
  %10 = add i64 %9, 1
  store i64 %10, ptr @gc_thread_count, align 8, !tbaa !16
  %11 = icmp ult i64 %10, 129
  br i1 %11, label %12, label %19

12:                                               ; preds = %8
  %13 = tail call align 8 ptr @llvm.threadlocal.address.p0(ptr align 8 @gc_my_id)
  store i64 %10, ptr %13, align 8, !tbaa !16
  %14 = tail call i64 @pthread_self() #21
  %15 = getelementptr inbounds [128 x %struct.GCThread], ptr @gc_threads, i64 0, i64 %9
  store i64 %14, ptr %15, align 16, !tbaa !30
  %16 = ptrtoint ptr %0 to i64
  %17 = getelementptr inbounds i8, ptr %15, i64 8
  store i64 %16, ptr %17, align 8, !tbaa !20
  %18 = getelementptr inbounds i8, ptr %15, i64 16
  tail call void @llvm.memset.p0.i64(ptr noundef nonnull align 16 dereferenceable(16) %18, i8 0, i64 16, i1 false)
  br label %19

19:                                               ; preds = %12, %8
  store atomic volatile i8 0, ptr @gc_lock release, align 1
  ret void
}

; Function Attrs: mustprogress nocallback nofree nosync nounwind speculatable willreturn memory(none)
declare nonnull ptr @llvm.threadlocal.address.p0(ptr nonnull) #4

; Function Attrs: mustprogress nofree nosync nounwind willreturn memory(none)
declare i64 @pthread_self() local_unnamed_addr #5

; Function Attrs: mustprogress nofree norecurse nosync nounwind willreturn memory(readwrite, argmem: none, inaccessiblemem: none) uwtable
define dso_local void @__threadon_gc_thread_exit() local_unnamed_addr #6 {
  %1 = tail call align 8 ptr @llvm.threadlocal.address.p0(ptr align 8 @gc_my_id)
  %2 = load i64, ptr %1, align 8
  %3 = add i64 %2, -1
  %4 = icmp ult i64 %3, 128
  br i1 %4, label %5, label %7

5:                                                ; preds = %0
  %6 = getelementptr inbounds [128 x %struct.GCThread], ptr @gc_threads, i64 0, i64 %3, i32 1
  store i64 0, ptr %6, align 8, !tbaa !20
  store i64 0, ptr %1, align 8, !tbaa !16
  br label %7

7:                                                ; preds = %5, %0
  ret void
}

; Function Attrs: nounwind uwtable
define dso_local void @__threadon_gc_collect() local_unnamed_addr #0 {
  %1 = alloca %struct.timespec, align 8
  %2 = alloca %struct.timespec, align 8
  %3 = alloca %struct.timespec, align 8
  %4 = alloca %struct.timespec, align 8
  %5 = alloca %struct.timespec, align 8
  %6 = alloca %struct.timespec, align 8
  %7 = load i1, ptr @gc_env_initialized, align 4
  br i1 %7, label %20, label %8

8:                                                ; preds = %0
  %9 = tail call ptr @getenv(ptr noundef nonnull @__gc_str_1) #15
  %10 = icmp eq ptr %9, null
  br i1 %10, label %19, label %11

11:                                               ; preds = %8
  %12 = load i8, ptr %9, align 1
  %13 = icmp eq i8 %12, 48
  br i1 %13, label %14, label %18

14:                                               ; preds = %11
  %15 = getelementptr inbounds i8, ptr %9, i64 1
  %16 = load i8, ptr %15, align 1
  %17 = icmp eq i8 %16, 0
  br i1 %17, label %19, label %18

18:                                               ; preds = %14, %11
  store i1 true, ptr @gc_stats, align 4
  br label %19

19:                                               ; preds = %18, %14, %8
  store i1 true, ptr @gc_env_initialized, align 4
  br label %20

20:                                               ; preds = %0, %19
  %21 = load i1, ptr @gc_stats, align 4
  br i1 %21, label %22, label %29

22:                                               ; preds = %20
  call void @llvm.lifetime.start.p0(i64 16, ptr nonnull %6) #19
  %23 = call i32 @clock_gettime(i32 noundef 1, ptr noundef nonnull %6) #15
  %24 = load i64, ptr %6, align 8, !tbaa !21
  %25 = mul i64 %24, -1000000000
  %26 = getelementptr inbounds i8, ptr %6, i64 8
  %27 = load i64, ptr %26, align 8, !tbaa !23
  %28 = sub i64 %25, %27
  call void @llvm.lifetime.end.p0(i64 16, ptr nonnull %6) #19
  br label %29

29:                                               ; preds = %20, %22
  %30 = phi i64 [ %28, %22 ], [ 0, %20 ]
  %31 = atomicrmw add ptr @gc_collections, i64 1 monotonic, align 8
  %32 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %33 = icmp eq i8 %32, 0
  br i1 %33, label %38, label %34

34:                                               ; preds = %29, %34
  %35 = call i32 @sched_yield() #15
  %36 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %37 = icmp eq i8 %36, 0
  br i1 %37, label %38, label %34, !llvm.loop !5

38:                                               ; preds = %34, %29
  store atomic i64 1, ptr @gc_collecting seq_cst, align 8
  %39 = atomicrmw add ptr @gc_epoch, i64 1 seq_cst, align 8
  %40 = atomicrmw add ptr @gc_snap_gen, i64 1 seq_cst, align 8
  store atomic volatile i8 0, ptr @gc_lock release, align 1
  %41 = load i1, ptr @gc_stats, align 4
  br i1 %41, label %42, label %49

42:                                               ; preds = %38
  call void @llvm.lifetime.start.p0(i64 16, ptr nonnull %5) #19
  %43 = call i32 @clock_gettime(i32 noundef 1, ptr noundef nonnull %5) #15
  %44 = load i64, ptr %5, align 8, !tbaa !21
  %45 = mul i64 %44, -1000000000
  %46 = getelementptr inbounds i8, ptr %5, i64 8
  %47 = load i64, ptr %46, align 8, !tbaa !23
  %48 = sub i64 %45, %47
  call void @llvm.lifetime.end.p0(i64 16, ptr nonnull %5) #19
  br label %49

49:                                               ; preds = %38, %42
  %50 = phi i64 [ %48, %42 ], [ 0, %38 ]
  call fastcc void @gc_capture_stack() #18
  call fastcc void @gc_mark_roots() #18
  %51 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %52 = icmp eq i8 %51, 0
  br i1 %52, label %57, label %53

53:                                               ; preds = %49, %53
  %54 = call i32 @sched_yield() #15
  %55 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %56 = icmp eq i8 %55, 0
  br i1 %56, label %57, label %53, !llvm.loop !5

57:                                               ; preds = %53, %49
  %58 = atomicrmw add ptr @gc_snap_gen, i64 1 seq_cst, align 8
  store atomic volatile i8 0, ptr @gc_lock release, align 1
  call fastcc void @gc_capture_stack() #18
  call fastcc void @gc_mark_roots() #18
  %59 = load i1, ptr @gc_stats, align 4
  br i1 %59, label %60, label %85

60:                                               ; preds = %57
  call void @llvm.lifetime.start.p0(i64 16, ptr nonnull %4) #19
  %61 = call i32 @clock_gettime(i32 noundef 1, ptr noundef nonnull %4) #15
  %62 = load i64, ptr %4, align 8, !tbaa !21
  %63 = mul i64 %62, 1000000000
  %64 = getelementptr inbounds i8, ptr %4, i64 8
  %65 = load i64, ptr %64, align 8, !tbaa !23
  call void @llvm.lifetime.end.p0(i64 16, ptr nonnull %4) #19
  %66 = add i64 %65, %50
  %67 = add i64 %66, %63
  %68 = load atomic i64, ptr @gc_max_mark_ns monotonic, align 8
  br label %69

69:                                               ; preds = %72, %60
  %70 = phi i64 [ %68, %60 ], [ %75, %72 ]
  %71 = icmp ult i64 %70, %67
  br i1 %71, label %72, label %76

72:                                               ; preds = %69
  %73 = cmpxchg ptr @gc_max_mark_ns, i64 %70, i64 %67 monotonic monotonic, align 8
  %74 = extractvalue { i64, i1 } %73, 1
  %75 = extractvalue { i64, i1 } %73, 0
  br i1 %74, label %76, label %69, !llvm.loop !26

76:                                               ; preds = %72, %69
  %77 = load i1, ptr @gc_stats, align 4
  br i1 %77, label %78, label %85

78:                                               ; preds = %76
  call void @llvm.lifetime.start.p0(i64 16, ptr nonnull %3) #19
  %79 = call i32 @clock_gettime(i32 noundef 1, ptr noundef nonnull %3) #15
  %80 = load i64, ptr %3, align 8, !tbaa !21
  %81 = mul i64 %80, -1000000000
  %82 = getelementptr inbounds i8, ptr %3, i64 8
  %83 = load i64, ptr %82, align 8, !tbaa !23
  %84 = sub i64 %81, %83
  call void @llvm.lifetime.end.p0(i64 16, ptr nonnull %3) #19
  br label %85

85:                                               ; preds = %57, %76, %78
  %86 = phi i64 [ %84, %78 ], [ 0, %76 ], [ 0, %57 ]
  %87 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %88 = icmp eq i8 %87, 0
  br i1 %88, label %93, label %89

89:                                               ; preds = %85, %89
  %90 = call i32 @sched_yield() #15
  %91 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %92 = icmp eq i8 %91, 0
  br i1 %92, label %93, label %89, !llvm.loop !5

93:                                               ; preds = %89, %85
  %94 = load atomic i64, ptr @gc_epoch seq_cst, align 8
  %95 = load i64, ptr @gc_head, align 8, !tbaa !16
  %96 = icmp eq i64 %95, 0
  br i1 %96, label %110, label %97

97:                                               ; preds = %93, %107
  %98 = phi ptr [ %108, %107 ], [ @gc_head, %93 ]
  %99 = phi i64 [ %102, %107 ], [ %95, %93 ]
  %100 = inttoptr i64 %99 to ptr
  %101 = getelementptr inbounds i8, ptr %100, i64 24
  %102 = load i64, ptr %101, align 8, !tbaa !17
  %103 = getelementptr inbounds i8, ptr %100, i64 16
  %104 = load atomic i64, ptr %103 seq_cst, align 8
  %105 = icmp eq i64 %104, %94
  br i1 %105, label %107, label %106

106:                                              ; preds = %97
  store i64 %102, ptr %98, align 8, !tbaa !16
  call void @free(ptr noundef nonnull %100) #16
  br label %107

107:                                              ; preds = %106, %97
  %108 = phi ptr [ %98, %106 ], [ %101, %97 ]
  %109 = icmp eq i64 %102, 0
  br i1 %109, label %110, label %97, !llvm.loop !31

110:                                              ; preds = %107, %93
  store atomic volatile i8 0, ptr @gc_lock release, align 1
  %111 = load i1, ptr @gc_stats, align 4
  br i1 %111, label %112, label %137

112:                                              ; preds = %110
  call void @llvm.lifetime.start.p0(i64 16, ptr nonnull %2) #19
  %113 = call i32 @clock_gettime(i32 noundef 1, ptr noundef nonnull %2) #15
  %114 = load i64, ptr %2, align 8, !tbaa !21
  %115 = mul i64 %114, 1000000000
  %116 = getelementptr inbounds i8, ptr %2, i64 8
  %117 = load i64, ptr %116, align 8, !tbaa !23
  call void @llvm.lifetime.end.p0(i64 16, ptr nonnull %2) #19
  %118 = add i64 %117, %86
  %119 = add i64 %118, %115
  %120 = load atomic i64, ptr @gc_max_sweep_ns monotonic, align 8
  br label %121

121:                                              ; preds = %124, %112
  %122 = phi i64 [ %120, %112 ], [ %127, %124 ]
  %123 = icmp ult i64 %122, %119
  br i1 %123, label %124, label %128

124:                                              ; preds = %121
  %125 = cmpxchg ptr @gc_max_sweep_ns, i64 %122, i64 %119 monotonic monotonic, align 8
  %126 = extractvalue { i64, i1 } %125, 1
  %127 = extractvalue { i64, i1 } %125, 0
  br i1 %126, label %128, label %121, !llvm.loop !26

128:                                              ; preds = %121, %124
  call void @llvm.lifetime.start.p0(i64 16, ptr nonnull %1) #19
  %129 = call i32 @clock_gettime(i32 noundef 1, ptr noundef nonnull %1) #15
  %130 = load i64, ptr %1, align 8, !tbaa !21
  %131 = mul i64 %130, 1000000000
  %132 = getelementptr inbounds i8, ptr %1, i64 8
  %133 = load i64, ptr %132, align 8, !tbaa !23
  call void @llvm.lifetime.end.p0(i64 16, ptr nonnull %1) #19
  %134 = add i64 %133, %30
  %135 = add i64 %134, %131
  %136 = atomicrmw add ptr @gc_sum_collector_ns, i64 %135 monotonic, align 8
  br label %137

137:                                              ; preds = %128, %110
  %138 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %139 = icmp eq i8 %138, 0
  br i1 %139, label %144, label %140

140:                                              ; preds = %137, %140
  %141 = call i32 @sched_yield() #15
  %142 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %143 = icmp eq i8 %142, 0
  br i1 %143, label %144, label %140, !llvm.loop !5

144:                                              ; preds = %140, %137
  store atomic i64 0, ptr @gc_collecting seq_cst, align 8
  store atomic volatile i8 0, ptr @gc_lock release, align 1
  ret void
}

; Function Attrs: nounwind uwtable
define internal fastcc void @gc_mark_roots() unnamed_addr #0 {
  %1 = tail call noalias ptr @malloc(i64 noundef 2048) #16
  %2 = icmp eq ptr %1, null
  br i1 %2, label %283, label %3

3:                                                ; preds = %0
  %4 = load i64, ptr @gc_root_count, align 8, !tbaa !16
  %5 = icmp ugt i64 %4, 1
  br i1 %5, label %12, label %6

6:                                                ; preds = %29, %3
  %7 = phi i64 [ 256, %3 ], [ %31, %29 ]
  %8 = phi i64 [ 0, %3 ], [ %32, %29 ]
  %9 = phi ptr [ %1, %3 ], [ %33, %29 ]
  %10 = load i64, ptr @gc_thread_count, align 8, !tbaa !16
  %11 = icmp eq i64 %10, 0
  br i1 %11, label %88, label %93

12:                                               ; preds = %3, %29
  %13 = phi i64 [ %30, %29 ], [ %4, %3 ]
  %14 = phi i64 [ %34, %29 ], [ 0, %3 ]
  %15 = phi ptr [ %33, %29 ], [ %1, %3 ]
  %16 = phi i64 [ %32, %29 ], [ 0, %3 ]
  %17 = phi i64 [ %31, %29 ], [ 256, %3 ]
  %18 = or disjoint i64 %14, 1
  %19 = getelementptr inbounds [512 x i64], ptr @gc_roots, i64 0, i64 %14
  %20 = load i64, ptr %19, align 16, !tbaa !16
  %21 = getelementptr inbounds [512 x i64], ptr @gc_roots, i64 0, i64 %18
  %22 = load i64, ptr %21, align 8, !tbaa !16
  %23 = icmp ult i64 %22, 8
  br i1 %23, label %29, label %24

24:                                               ; preds = %12
  %25 = load i64, ptr @gc_min, align 8
  %26 = load i64, ptr @gc_max, align 8
  br label %37

27:                                               ; preds = %82
  %28 = load i64, ptr @gc_root_count, align 8, !tbaa !16
  br label %29

29:                                               ; preds = %27, %12
  %30 = phi i64 [ %13, %12 ], [ %28, %27 ]
  %31 = phi i64 [ %17, %12 ], [ %83, %27 ]
  %32 = phi i64 [ %16, %12 ], [ %84, %27 ]
  %33 = phi ptr [ %15, %12 ], [ %85, %27 ]
  %34 = add i64 %14, 2
  %35 = or disjoint i64 %34, 1
  %36 = icmp ult i64 %35, %30
  br i1 %36, label %12, label %6, !llvm.loop !32

37:                                               ; preds = %24, %82
  %38 = phi i64 [ 8, %24 ], [ %86, %82 ]
  %39 = phi i64 [ 0, %24 ], [ %38, %82 ]
  %40 = phi ptr [ %15, %24 ], [ %85, %82 ]
  %41 = phi i64 [ %16, %24 ], [ %84, %82 ]
  %42 = phi i64 [ %17, %24 ], [ %83, %82 ]
  %43 = add i64 %39, %20
  %44 = inttoptr i64 %43 to ptr
  %45 = load volatile i64, ptr %44, align 8, !tbaa !16
  %46 = and i64 %45, -2
  %47 = icmp eq i64 %46, 0
  %48 = and i64 %45, 6
  %49 = icmp ne i64 %48, 0
  %50 = or i1 %47, %49
  %51 = icmp ult i64 %46, %25
  %52 = select i1 %50, i1 true, i1 %51
  br i1 %52, label %82, label %53

53:                                               ; preds = %37
  %54 = icmp ugt i64 %46, %26
  %55 = icmp ult i64 %45, 48
  %56 = or i1 %55, %54
  br i1 %56, label %82, label %57

57:                                               ; preds = %53
  %58 = add i64 %46, -48
  %59 = inttoptr i64 %58 to ptr
  %60 = load i64, ptr %59, align 8, !tbaa !7
  %61 = icmp eq i64 %60, 6073194554910330702
  br i1 %61, label %62, label %82

62:                                               ; preds = %57
  %63 = getelementptr inbounds i8, ptr %59, i64 8
  %64 = load i64, ptr %63, align 8, !tbaa !12
  %65 = icmp ult i64 %64, 48
  %66 = add i64 %64, %58
  %67 = icmp ult i64 %66, %46
  %68 = or i1 %65, %67
  br i1 %68, label %82, label %69

69:                                               ; preds = %62
  %70 = icmp eq i64 %41, %42
  br i1 %70, label %71, label %77

71:                                               ; preds = %69
  %72 = shl i64 %41, 4
  %73 = tail call ptr @realloc(ptr noundef %40, i64 noundef %72) #20
  %74 = icmp eq ptr %73, null
  br i1 %74, label %82, label %75

75:                                               ; preds = %71
  %76 = shl i64 %41, 1
  br label %77

77:                                               ; preds = %75, %69
  %78 = phi i64 [ %76, %75 ], [ %42, %69 ]
  %79 = phi ptr [ %73, %75 ], [ %40, %69 ]
  %80 = add i64 %41, 1
  %81 = getelementptr inbounds i64, ptr %79, i64 %41
  store i64 %46, ptr %81, align 8, !tbaa !16
  br label %82

82:                                               ; preds = %37, %53, %57, %62, %71, %77
  %83 = phi i64 [ %42, %37 ], [ %42, %53 ], [ %42, %62 ], [ %41, %71 ], [ %78, %77 ], [ %42, %57 ]
  %84 = phi i64 [ %41, %37 ], [ %41, %53 ], [ %41, %62 ], [ %41, %71 ], [ %80, %77 ], [ %41, %57 ]
  %85 = phi ptr [ %40, %37 ], [ %40, %53 ], [ %40, %62 ], [ %40, %71 ], [ %79, %77 ], [ %40, %57 ]
  %86 = add i64 %38, 8
  %87 = icmp ugt i64 %86, %22
  br i1 %87, label %27, label %37, !llvm.loop !33

88:                                               ; preds = %173, %6
  %89 = phi i64 [ %7, %6 ], [ %175, %173 ]
  %90 = phi i64 [ %8, %6 ], [ %176, %173 ]
  %91 = phi ptr [ %9, %6 ], [ %177, %173 ]
  %92 = icmp eq i64 %90, 0
  br i1 %92, label %281, label %182

93:                                               ; preds = %6, %173
  %94 = phi i64 [ %174, %173 ], [ %10, %6 ]
  %95 = phi i64 [ %178, %173 ], [ 0, %6 ]
  %96 = phi ptr [ %177, %173 ], [ %9, %6 ]
  %97 = phi i64 [ %176, %173 ], [ %8, %6 ]
  %98 = phi i64 [ %175, %173 ], [ %7, %6 ]
  %99 = getelementptr inbounds [128 x %struct.GCThread], ptr @gc_threads, i64 0, i64 %95
  %100 = getelementptr inbounds i8, ptr %99, i64 8
  %101 = load i64, ptr %100, align 8, !tbaa !20
  %102 = icmp eq i64 %101, 0
  br i1 %102, label %173, label %103

103:                                              ; preds = %93
  %104 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %105 = icmp eq i8 %104, 0
  br i1 %105, label %110, label %106

106:                                              ; preds = %103, %106
  %107 = tail call i32 @sched_yield() #15
  %108 = atomicrmw volatile xchg ptr @gc_lock, i8 1 acquire, align 1
  %109 = icmp eq i8 %108, 0
  br i1 %109, label %110, label %106, !llvm.loop !5

110:                                              ; preds = %106, %103
  %111 = getelementptr inbounds i8, ptr %99, i64 24
  %112 = load i64, ptr %111, align 8, !tbaa !25
  %113 = tail call i64 @llvm.umin.i64(i64 %112, i64 8192)
  %114 = icmp eq i64 %112, 0
  br i1 %114, label %117, label %115

115:                                              ; preds = %110
  %116 = getelementptr inbounds i8, ptr %99, i64 32
  br label %122

117:                                              ; preds = %167, %110
  %118 = phi i64 [ %98, %110 ], [ %168, %167 ]
  %119 = phi i64 [ %97, %110 ], [ %169, %167 ]
  %120 = phi ptr [ %96, %110 ], [ %170, %167 ]
  store atomic volatile i8 0, ptr @gc_lock release, align 1
  %121 = load i64, ptr @gc_thread_count, align 8, !tbaa !16
  br label %173

122:                                              ; preds = %115, %167
  %123 = phi i64 [ 0, %115 ], [ %171, %167 ]
  %124 = phi ptr [ %96, %115 ], [ %170, %167 ]
  %125 = phi i64 [ %97, %115 ], [ %169, %167 ]
  %126 = phi i64 [ %98, %115 ], [ %168, %167 ]
  %127 = getelementptr inbounds [8192 x i64], ptr %116, i64 0, i64 %123
  %128 = load i64, ptr %127, align 8, !tbaa !16
  %129 = and i64 %128, -2
  %130 = icmp eq i64 %129, 0
  %131 = and i64 %128, 6
  %132 = icmp ne i64 %131, 0
  %133 = or i1 %130, %132
  %134 = load i64, ptr @gc_min, align 8
  %135 = icmp ult i64 %129, %134
  %136 = select i1 %133, i1 true, i1 %135
  br i1 %136, label %167, label %137

137:                                              ; preds = %122
  %138 = load i64, ptr @gc_max, align 8, !tbaa !16
  %139 = icmp ugt i64 %129, %138
  %140 = icmp ult i64 %128, 48
  %141 = or i1 %140, %139
  br i1 %141, label %167, label %142

142:                                              ; preds = %137
  %143 = add i64 %129, -48
  %144 = inttoptr i64 %143 to ptr
  %145 = load i64, ptr %144, align 8, !tbaa !7
  %146 = icmp eq i64 %145, 6073194554910330702
  br i1 %146, label %147, label %167

147:                                              ; preds = %142
  %148 = getelementptr inbounds i8, ptr %144, i64 8
  %149 = load i64, ptr %148, align 8, !tbaa !12
  %150 = icmp ult i64 %149, 48
  %151 = add i64 %149, %143
  %152 = icmp ult i64 %151, %129
  %153 = or i1 %150, %152
  br i1 %153, label %167, label %154

154:                                              ; preds = %147
  %155 = icmp eq i64 %125, %126
  br i1 %155, label %156, label %162

156:                                              ; preds = %154
  %157 = shl i64 %125, 4
  %158 = tail call ptr @realloc(ptr noundef %124, i64 noundef %157) #20
  %159 = icmp eq ptr %158, null
  br i1 %159, label %167, label %160

160:                                              ; preds = %156
  %161 = shl i64 %125, 1
  br label %162

162:                                              ; preds = %160, %154
  %163 = phi i64 [ %161, %160 ], [ %126, %154 ]
  %164 = phi ptr [ %158, %160 ], [ %124, %154 ]
  %165 = add i64 %125, 1
  %166 = getelementptr inbounds i64, ptr %164, i64 %125
  store i64 %129, ptr %166, align 8, !tbaa !16
  br label %167

167:                                              ; preds = %122, %137, %142, %147, %156, %162
  %168 = phi i64 [ %126, %122 ], [ %126, %137 ], [ %126, %147 ], [ %125, %156 ], [ %163, %162 ], [ %126, %142 ]
  %169 = phi i64 [ %125, %122 ], [ %125, %137 ], [ %125, %147 ], [ %125, %156 ], [ %165, %162 ], [ %125, %142 ]
  %170 = phi ptr [ %124, %122 ], [ %124, %137 ], [ %124, %147 ], [ %124, %156 ], [ %164, %162 ], [ %124, %142 ]
  %171 = add nuw nsw i64 %123, 1
  %172 = icmp eq i64 %171, %113
  br i1 %172, label %117, label %122, !llvm.loop !34

173:                                              ; preds = %93, %117
  %174 = phi i64 [ %94, %93 ], [ %121, %117 ]
  %175 = phi i64 [ %98, %93 ], [ %118, %117 ]
  %176 = phi i64 [ %97, %93 ], [ %119, %117 ]
  %177 = phi ptr [ %96, %93 ], [ %120, %117 ]
  %178 = add nuw nsw i64 %95, 1
  %179 = icmp ult i64 %178, %174
  %180 = icmp ult i64 %95, 127
  %181 = and i1 %180, %179
  br i1 %181, label %93, label %88, !llvm.loop !35

182:                                              ; preds = %88, %276
  %183 = phi ptr [ %279, %276 ], [ %91, %88 ]
  %184 = phi i64 [ %278, %276 ], [ %90, %88 ]
  %185 = phi i64 [ %277, %276 ], [ %89, %88 ]
  %186 = add i64 %184, -1
  %187 = getelementptr inbounds i64, ptr %183, i64 %186
  %188 = load i64, ptr %187, align 8, !tbaa !16
  %189 = and i64 %188, -2
  %190 = icmp eq i64 %189, 0
  %191 = and i64 %188, 6
  %192 = icmp ne i64 %191, 0
  %193 = or i1 %190, %192
  %194 = load i64, ptr @gc_min, align 8
  %195 = icmp ult i64 %189, %194
  %196 = select i1 %193, i1 true, i1 %195
  br i1 %196, label %276, label %197

197:                                              ; preds = %182
  %198 = load i64, ptr @gc_max, align 8, !tbaa !16
  %199 = icmp ugt i64 %189, %198
  %200 = icmp ult i64 %188, 48
  %201 = or i1 %200, %199
  br i1 %201, label %276, label %202

202:                                              ; preds = %197
  %203 = add i64 %189, -48
  %204 = inttoptr i64 %203 to ptr
  %205 = load i64, ptr %204, align 8, !tbaa !7
  %206 = icmp eq i64 %205, 6073194554910330702
  br i1 %206, label %207, label %276

207:                                              ; preds = %202
  %208 = getelementptr inbounds i8, ptr %204, i64 8
  %209 = load i64, ptr %208, align 8, !tbaa !12
  %210 = icmp ult i64 %209, 48
  %211 = add i64 %209, %203
  %212 = icmp ult i64 %211, %189
  %213 = or i1 %210, %212
  br i1 %213, label %276, label %214, !llvm.loop !36

214:                                              ; preds = %207
  %215 = load atomic i64, ptr @gc_epoch seq_cst, align 8
  %216 = getelementptr inbounds i8, ptr %204, i64 16
  %217 = load atomic i64, ptr %216 seq_cst, align 8
  %218 = icmp eq i64 %217, %215
  br i1 %218, label %276, label %219, !llvm.loop !36

219:                                              ; preds = %214
  store atomic i64 %215, ptr %216 seq_cst, align 8
  %220 = load i64, ptr %208, align 8, !tbaa !12
  %221 = add i64 %220, %203
  %222 = add i64 %189, 8
  %223 = icmp ugt i64 %222, %221
  br i1 %223, label %276, label %224

224:                                              ; preds = %219, %270
  %225 = phi i64 [ %274, %270 ], [ %222, %219 ]
  %226 = phi i64 [ %225, %270 ], [ %189, %219 ]
  %227 = phi ptr [ %273, %270 ], [ %183, %219 ]
  %228 = phi i64 [ %272, %270 ], [ %186, %219 ]
  %229 = phi i64 [ %271, %270 ], [ %185, %219 ]
  %230 = inttoptr i64 %226 to ptr
  %231 = load volatile i64, ptr %230, align 8, !tbaa !16
  %232 = and i64 %231, -2
  %233 = icmp eq i64 %232, 0
  %234 = and i64 %231, 6
  %235 = icmp ne i64 %234, 0
  %236 = or i1 %233, %235
  %237 = load i64, ptr @gc_min, align 8
  %238 = icmp ult i64 %232, %237
  %239 = select i1 %236, i1 true, i1 %238
  br i1 %239, label %270, label %240

240:                                              ; preds = %224
  %241 = load i64, ptr @gc_max, align 8, !tbaa !16
  %242 = icmp ugt i64 %232, %241
  %243 = icmp ult i64 %231, 48
  %244 = or i1 %243, %242
  br i1 %244, label %270, label %245

245:                                              ; preds = %240
  %246 = add i64 %232, -48
  %247 = inttoptr i64 %246 to ptr
  %248 = load i64, ptr %247, align 8, !tbaa !7
  %249 = icmp eq i64 %248, 6073194554910330702
  br i1 %249, label %250, label %270

250:                                              ; preds = %245
  %251 = getelementptr inbounds i8, ptr %247, i64 8
  %252 = load i64, ptr %251, align 8, !tbaa !12
  %253 = icmp ult i64 %252, 48
  %254 = add i64 %252, %246
  %255 = icmp ult i64 %254, %232
  %256 = or i1 %253, %255
  br i1 %256, label %270, label %257

257:                                              ; preds = %250
  %258 = icmp eq i64 %228, %229
  br i1 %258, label %259, label %265

259:                                              ; preds = %257
  %260 = shl i64 %228, 4
  %261 = tail call ptr @realloc(ptr noundef %227, i64 noundef %260) #20
  %262 = icmp eq ptr %261, null
  br i1 %262, label %270, label %263

263:                                              ; preds = %259
  %264 = shl i64 %228, 1
  br label %265

265:                                              ; preds = %263, %257
  %266 = phi i64 [ %264, %263 ], [ %229, %257 ]
  %267 = phi ptr [ %261, %263 ], [ %227, %257 ]
  %268 = add i64 %228, 1
  %269 = getelementptr inbounds i64, ptr %267, i64 %228
  store i64 %232, ptr %269, align 8, !tbaa !16
  br label %270

270:                                              ; preds = %224, %240, %245, %250, %259, %265
  %271 = phi i64 [ %229, %224 ], [ %229, %240 ], [ %229, %250 ], [ %228, %259 ], [ %266, %265 ], [ %229, %245 ]
  %272 = phi i64 [ %228, %224 ], [ %228, %240 ], [ %228, %250 ], [ %228, %259 ], [ %268, %265 ], [ %228, %245 ]
  %273 = phi ptr [ %227, %224 ], [ %227, %240 ], [ %227, %250 ], [ %227, %259 ], [ %267, %265 ], [ %227, %245 ]
  %274 = add i64 %225, 8
  %275 = icmp ugt i64 %274, %221
  br i1 %275, label %276, label %224, !llvm.loop !37

276:                                              ; preds = %270, %219, %207, %202, %197, %182, %214
  %277 = phi i64 [ %185, %214 ], [ %185, %182 ], [ %185, %197 ], [ %185, %202 ], [ %185, %207 ], [ %185, %219 ], [ %271, %270 ]
  %278 = phi i64 [ %186, %214 ], [ %186, %182 ], [ %186, %197 ], [ %186, %202 ], [ %186, %207 ], [ %186, %219 ], [ %272, %270 ]
  %279 = phi ptr [ %183, %214 ], [ %183, %182 ], [ %183, %197 ], [ %183, %202 ], [ %183, %207 ], [ %183, %219 ], [ %273, %270 ]
  %280 = icmp eq i64 %278, 0
  br i1 %280, label %281, label %182

281:                                              ; preds = %276, %88
  %282 = phi ptr [ %91, %88 ], [ %279, %276 ]
  tail call void @free(ptr noundef %282) #16
  br label %283

283:                                              ; preds = %0, %281
  ret void
}

; Function Attrs: mustprogress nofree norecurse nounwind willreturn memory(read, argmem: readwrite, inaccessiblemem: none) uwtable
define dso_local range(i64 0, 2) i64 @__threadon_gc_is_unique(ptr noundef %0) local_unnamed_addr #7 {
  %2 = icmp eq ptr %0, null
  br i1 %2, label %21, label %3

3:                                                ; preds = %1
  %4 = ptrtoint ptr %0 to i64
  %5 = load i64, ptr @gc_min, align 8, !tbaa !16
  %6 = icmp ugt i64 %5, %4
  br i1 %6, label %21, label %7

7:                                                ; preds = %3
  %8 = load i64, ptr @gc_max, align 8, !tbaa !16
  %9 = icmp ult i64 %8, %4
  %10 = icmp ult ptr %0, inttoptr (i64 48 to ptr)
  %11 = or i1 %10, %9
  br i1 %11, label %21, label %12

12:                                               ; preds = %7
  %13 = getelementptr inbounds i8, ptr %0, i64 -48
  %14 = load i64, ptr %13, align 8, !tbaa !7
  %15 = icmp eq i64 %14, 6073194554910330702
  br i1 %15, label %16, label %21

16:                                               ; preds = %12
  %17 = getelementptr inbounds i8, ptr %0, i64 -16
  %18 = load atomic i64, ptr %17 seq_cst, align 8
  %19 = icmp ult i64 %18, 2
  %20 = zext i1 %19 to i64
  br label %21

21:                                               ; preds = %7, %3, %12, %16, %1
  %22 = phi i64 [ 1, %1 ], [ 0, %7 ], [ 0, %3 ], [ %20, %16 ], [ 0, %12 ]
  ret i64 %22
}

; Function Attrs: mustprogress nofree norecurse nounwind willreturn memory(read, argmem: readwrite, inaccessiblemem: none) uwtable
define dso_local void @__threadon_gc_retain(ptr noundef %0) local_unnamed_addr #7 {
  %2 = icmp eq ptr %0, null
  br i1 %2, label %19, label %3

3:                                                ; preds = %1
  %4 = ptrtoint ptr %0 to i64
  %5 = load i64, ptr @gc_min, align 8, !tbaa !16
  %6 = icmp ugt i64 %5, %4
  br i1 %6, label %19, label %7

7:                                                ; preds = %3
  %8 = load i64, ptr @gc_max, align 8, !tbaa !16
  %9 = icmp ult i64 %8, %4
  %10 = icmp ult ptr %0, inttoptr (i64 48 to ptr)
  %11 = or i1 %10, %9
  br i1 %11, label %19, label %12

12:                                               ; preds = %7
  %13 = getelementptr inbounds i8, ptr %0, i64 -48
  %14 = load i64, ptr %13, align 8, !tbaa !7
  %15 = icmp eq i64 %14, 6073194554910330702
  br i1 %15, label %16, label %19

16:                                               ; preds = %12
  %17 = getelementptr inbounds i8, ptr %0, i64 -16
  %18 = atomicrmw add ptr %17, i64 1 seq_cst, align 8
  br label %19

19:                                               ; preds = %7, %3, %12, %16, %1
  ret void
}

; Function Attrs: mustprogress nofree norecurse nounwind willreturn memory(read, argmem: readwrite, inaccessiblemem: none) uwtable
define dso_local void @__threadon_gc_release(ptr noundef %0) local_unnamed_addr #7 {
  %2 = icmp eq ptr %0, null
  br i1 %2, label %21, label %3

3:                                                ; preds = %1
  %4 = ptrtoint ptr %0 to i64
  %5 = load i64, ptr @gc_min, align 8, !tbaa !16
  %6 = icmp ugt i64 %5, %4
  br i1 %6, label %21, label %7

7:                                                ; preds = %3
  %8 = load i64, ptr @gc_max, align 8, !tbaa !16
  %9 = icmp ult i64 %8, %4
  %10 = icmp ult ptr %0, inttoptr (i64 48 to ptr)
  %11 = or i1 %10, %9
  br i1 %11, label %21, label %12

12:                                               ; preds = %7
  %13 = getelementptr inbounds i8, ptr %0, i64 -48
  %14 = load i64, ptr %13, align 8, !tbaa !7
  %15 = icmp eq i64 %14, 6073194554910330702
  br i1 %15, label %16, label %21

16:                                               ; preds = %12
  %17 = getelementptr inbounds i8, ptr %0, i64 -16
  %18 = atomicrmw sub ptr %17, i64 1 seq_cst, align 8
  %19 = icmp eq i64 %18, 0
  br i1 %19, label %20, label %21

20:                                               ; preds = %16
  store atomic i64 0, ptr %17 seq_cst, align 8
  br label %21

21:                                               ; preds = %7, %3, %16, %20, %12, %1
  ret void
}

; Function Attrs: nofree nounwind uwtable
define dso_local void @__threadon_gc_shutdown() local_unnamed_addr #8 {
  %1 = load i1, ptr @gc_stats, align 4
  br i1 %1, label %2, label %27

2:                                                ; preds = %0
  %3 = load i64, ptr @gc_collections, align 8, !tbaa !16
  %4 = load i64, ptr @gc_snapshot_count, align 8, !tbaa !16
  %5 = load i64, ptr @gc_max_snapshot_ns, align 8, !tbaa !16
  %6 = uitofp i64 %5 to double
  %7 = fdiv double %6, 1.000000e+03
  %8 = icmp eq i64 %4, 0
  br i1 %8, label %15, label %9

9:                                                ; preds = %2
  %10 = load i64, ptr @gc_sum_snapshot_ns, align 8, !tbaa !16
  %11 = uitofp i64 %10 to double
  %12 = uitofp i64 %4 to double
  %13 = fdiv double %11, %12
  %14 = fdiv double %13, 1.000000e+03
  br label %15

15:                                               ; preds = %2, %9
  %16 = phi double [ %14, %9 ], [ 0.000000e+00, %2 ]
  %17 = load i64, ptr @gc_max_mark_ns, align 8, !tbaa !16
  %18 = uitofp i64 %17 to double
  %19 = fdiv double %18, 1.000000e+03
  %20 = load i64, ptr @gc_max_sweep_ns, align 8, !tbaa !16
  %21 = uitofp i64 %20 to double
  %22 = fdiv double %21, 1.000000e+03
  %23 = load i64, ptr @gc_sum_collector_ns, align 8, !tbaa !16
  %24 = uitofp i64 %23 to double
  %25 = fdiv double %24, 1.000000e+06
  %26 = tail call i32 (ptr, ...) @printf(ptr noundef nonnull dereferenceable(1) @__gc_str, i64 noundef %3, i64 noundef %4, double noundef %7, double noundef %16, double noundef %19, double noundef %22, double noundef %25) #18
  br label %27

27:                                               ; preds = %15, %0
  ret void
}

; Function Attrs: nofree nounwind
declare noundef i32 @printf(ptr nocapture noundef readonly, ...) local_unnamed_addr #9

; Function Attrs: nofree nounwind memory(read)
declare noundef ptr @getenv(ptr nocapture noundef) local_unnamed_addr #10

; Function Attrs: nounwind
declare i32 @sched_yield() local_unnamed_addr #2

; Function Attrs: mustprogress nocallback nofree nosync nounwind willreturn memory(none)
declare ptr @llvm.frameaddress.p0(i32 immarg) #11

; Function Attrs: nounwind
declare void @free(ptr noundef) local_unnamed_addr #2

; Function Attrs: mustprogress nounwind willreturn allockind("realloc") allocsize(1) memory(argmem: readwrite, inaccessiblemem: readwrite)
declare noalias noundef ptr @realloc(ptr allocptr nocapture noundef, i64 noundef) local_unnamed_addr #12

; Function Attrs: nounwind
declare i32 @clock_gettime(i32 noundef, ptr noundef) local_unnamed_addr #2

; Function Attrs: nocallback nofree nosync nounwind speculatable willreturn memory(none)
declare i64 @llvm.umin.i64(i64, i64) #13

; Function Attrs: nocallback nofree nounwind willreturn memory(argmem: write)
declare void @llvm.memset.p0.i64(ptr nocapture writeonly, i8, i64, i1 immarg) #14

attributes #0 = { nounwind uwtable "min-legal-vector-width"="0" "no-builtin-free" "no-builtin-malloc" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #1 = { mustprogress nocallback nofree nosync nounwind willreturn memory(argmem: readwrite) }
attributes #2 = { nounwind "no-builtin-free" "no-builtin-malloc" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #3 = { cold noreturn nounwind "no-builtin-free" "no-builtin-malloc" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #4 = { mustprogress nocallback nofree nosync nounwind speculatable willreturn memory(none) }
attributes #5 = { mustprogress nofree nosync nounwind willreturn memory(none) "no-builtin-free" "no-builtin-malloc" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #6 = { mustprogress nofree norecurse nosync nounwind willreturn memory(readwrite, argmem: none, inaccessiblemem: none) uwtable "min-legal-vector-width"="0" "no-builtin-free" "no-builtin-malloc" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #7 = { mustprogress nofree norecurse nounwind willreturn memory(read, argmem: readwrite, inaccessiblemem: none) uwtable "min-legal-vector-width"="0" "no-builtin-free" "no-builtin-malloc" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #8 = { nofree nounwind uwtable "min-legal-vector-width"="0" "no-builtin-free" "no-builtin-malloc" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #9 = { nofree nounwind "no-builtin-free" "no-builtin-malloc" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #10 = { nofree nounwind memory(read) "no-builtin-free" "no-builtin-malloc" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #11 = { mustprogress nocallback nofree nosync nounwind willreturn memory(none) }
attributes #12 = { mustprogress nounwind willreturn allockind("realloc") allocsize(1) memory(argmem: readwrite, inaccessiblemem: readwrite) "alloc-family"="malloc" "no-builtin-free" "no-builtin-malloc" "no-trapping-math"="true" "stack-protector-buffer-size"="8" "target-cpu"="x86-64" "target-features"="+cmov,+cx8,+fxsr,+mmx,+sse,+sse2,+x87" "tune-cpu"="generic" }
attributes #13 = { nocallback nofree nosync nounwind speculatable willreturn memory(none) }
attributes #14 = { nocallback nofree nounwind willreturn memory(argmem: write) }
attributes #15 = { nounwind "no-builtin-free" "no-builtin-malloc" }
attributes #16 = { nobuiltin nounwind "no-builtin-free" "no-builtin-malloc" }
attributes #17 = { cold noreturn nounwind "no-builtin-free" "no-builtin-malloc" }
attributes #18 = { "no-builtin-free" "no-builtin-malloc" }
attributes #19 = { nounwind }
attributes #20 = { nounwind allocsize(1) "no-builtin-free" "no-builtin-malloc" }
attributes #21 = { nounwind willreturn memory(none) "no-builtin-free" "no-builtin-malloc" }

!llvm.module.flags = !{!0, !1, !2, !3}
!llvm.ident = !{!4}

!0 = !{i32 1, !"wchar_size", i32 4}
!1 = !{i32 8, !"PIC Level", i32 2}
!2 = !{i32 7, !"PIE Level", i32 2}
!3 = !{i32 7, !"uwtable", i32 2}
!4 = !{!"Debian clang version 19.1.7 (3+b1)"}
!5 = distinct !{!5, !6}
!6 = !{!"llvm.loop.mustprogress"}
!7 = !{!8, !9, i64 0}
!8 = !{!"GCBlock", !9, i64 0, !9, i64 8, !9, i64 16, !9, i64 24, !9, i64 32, !9, i64 40}
!9 = !{!"long", !10, i64 0}
!10 = !{!"omnipotent char", !11, i64 0}
!11 = !{!"Simple C/C++ TBAA"}
!12 = !{!8, !9, i64 8}
!13 = !{!8, !9, i64 32}
!14 = !{!8, !9, i64 40}
!15 = !{!8, !9, i64 16}
!16 = !{!9, !9, i64 0}
!17 = !{!8, !9, i64 24}
!18 = !{!19, !9, i64 16}
!19 = !{!"", !9, i64 0, !9, i64 8, !9, i64 16, !9, i64 24, !10, i64 32}
!20 = !{!19, !9, i64 8}
!21 = !{!22, !9, i64 0}
!22 = !{!"timespec", !9, i64 0, !9, i64 8}
!23 = !{!22, !9, i64 8}
!24 = distinct !{!24, !6}
!25 = !{!19, !9, i64 24}
!26 = distinct !{!26, !6}
!27 = distinct !{!27, !6}
!28 = distinct !{!28, !6}
!29 = distinct !{!29, !6}
!30 = !{!19, !9, i64 0}
!31 = distinct !{!31, !6}
!32 = distinct !{!32, !6}
!33 = distinct !{!33, !6}
!34 = distinct !{!34, !6}
!35 = distinct !{!35, !6}
!36 = distinct !{!36, !6}
!37 = distinct !{!37, !6}
